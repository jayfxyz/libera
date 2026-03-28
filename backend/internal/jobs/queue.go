package jobs

import (
	"context"
	"database/sql"
	"log"
	"sync"

	"github.com/web-libation/backend/internal/audible"
)

type DownloadJob struct {
	ID               string
	BookID           int64
	AudibleID        string
	AccountID        int64
	AudibleAccountID string // sidecar account_id (e.g. amzn1.account.xxx)
	Title            string
	Format           string
	OutputDir        string
}

type ProgressEvent struct {
	JobID   string  `json:"job_id"`
	BookID  int64   `json:"book_id"`
	Status  string  `json:"status"` // queued, downloading, decrypting, done, error
	Percent float64 `json:"percent"`
	Message string  `json:"message,omitempty"`
}

type Queue struct {
	jobs      chan DownloadJob
	events    chan ProgressEvent
	subs      map[chan ProgressEvent]struct{}
	subsMu    sync.Mutex
	workers   int
	audible   *audible.Client
	db        *sql.DB
	wg        sync.WaitGroup
	cancelCtx context.Context
	cancel    context.CancelFunc
	state     map[string]ProgressEvent
	stateMu   sync.Mutex
}

func NewQueue(workers int, audible *audible.Client, db *sql.DB) *Queue {
	ctx, cancel := context.WithCancel(context.Background())
	return &Queue{
		jobs:      make(chan DownloadJob, 100),
		events:    make(chan ProgressEvent, 256),
		subs:      make(map[chan ProgressEvent]struct{}),
		workers:   workers,
		audible:   audible,
		db:        db,
		cancelCtx: ctx,
		cancel:    cancel,
		state:     map[string]ProgressEvent{},
	}
}

func (q *Queue) Start() {
	// Fan out events to all subscribers
	go q.broadcast()

	for i := 0; i < q.workers; i++ {
		q.wg.Add(1)
		go q.worker()
	}
}

func (q *Queue) Stop() {
	q.cancel()
	q.wg.Wait()
	close(q.events)
}

func (q *Queue) Enqueue(job DownloadJob) {
	q.jobs <- job
	q.emit(ProgressEvent{JobID: job.ID, BookID: job.BookID, Status: "queued", Percent: 0})
}

func (q *Queue) Subscribe() chan ProgressEvent {
	ch := make(chan ProgressEvent, 32)
	q.subsMu.Lock()
	q.subs[ch] = struct{}{}
	q.subsMu.Unlock()
	return ch
}

func (q *Queue) Unsubscribe(ch chan ProgressEvent) {
	q.subsMu.Lock()
	delete(q.subs, ch)
	q.subsMu.Unlock()
	close(ch)
}

func (q *Queue) emit(e ProgressEvent) {
	select {
	case q.events <- e:
	default:
		log.Printf("progress event buffer full, dropping event for job %s", e.JobID)
	}
}

func (q *Queue) broadcast() {
	for e := range q.events {
		q.subsMu.Lock()
		for ch := range q.subs {
			select {
			case ch <- e:
			default:
			}
		}
		q.subsMu.Unlock()
	}
}

func (q *Queue) setStatus(jobID string, status string, pct float64, msg string) {
	q.stateMu.Lock()
	e, ok := q.state[jobID]
	if !ok {
		e = ProgressEvent{JobID: jobID}
	}
	e.Status = status
	e.Percent = pct
	e.Message = msg
	q.state[jobID] = e
	q.stateMu.Unlock()
	q.emit(e)
}

func (q *Queue) markLiberated(bookID int64, format string) {
	q.db.Exec(`UPDATE library_books SET liberation_status = 'liberated', last_downloaded = CURRENT_TIMESTAMP, last_format = ? WHERE book_id = ?`, format, bookID)
}

func (q *Queue) markError(bookID int64) {
	q.db.Exec(`UPDATE library_books SET liberation_status = 'error' WHERE book_id = ? AND liberation_status != 'liberated'`, bookID)
}

func (q *Queue) ListJobs() []ProgressEvent {
	q.stateMu.Lock()
	defer q.stateMu.Unlock()
	out := make([]ProgressEvent, 0, len(q.state))
	for _, e := range q.state {
		out = append(out, e)
	}
	return out
}

func (q *Queue) worker() {
	defer q.wg.Done()
	for {
		select {
		case <-q.cancelCtx.Done():
			return
		case job, ok := <-q.jobs:
			if !ok {
				return
			}
			q.process(job)
		}
	}
}
