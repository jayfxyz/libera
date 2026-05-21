package jobs

import (
	"context"
	"database/sql"
	"log"
	"sync"

	"github.com/web-libation/backend/internal/audible"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
)

type DownloadJob struct {
	ID               string
	BookID           int64
	AudibleID        string
	AccountID        int64
	AudibleAccountID string // sidecar account_id (e.g. amzn1.account.xxx)
	Title            string
	Authors          string // comma-separated, used in filename templates
	Narrators        string
	SeriesName       string
	SeriesIndex      string
	Language         string
	LengthMinutes    int
	DateAdded        string
	Year             string
	DurationH        string
	Format           string
	OutputDir        string
	FilenameTemplate string
	TraceCarrier     map[string]string // serialized W3C trace context for cross-goroutine propagation
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
	cancels   map[string]context.CancelFunc
	cancelsMu sync.Mutex
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
		cancels:   map[string]context.CancelFunc{},
	}
}

func (q *Queue) registerCancel(jobID string, fn context.CancelFunc) {
	q.cancelsMu.Lock()
	q.cancels[jobID] = fn
	q.cancelsMu.Unlock()
}

func (q *Queue) deregisterCancel(jobID string) {
	q.cancelsMu.Lock()
	delete(q.cancels, jobID)
	q.cancelsMu.Unlock()
}

// Cancel stops an in-flight download job. Returns false if the job is not running.
func (q *Queue) Cancel(jobID string) bool {
	q.cancelsMu.Lock()
	fn, ok := q.cancels[jobID]
	if ok {
		delete(q.cancels, jobID)
	}
	q.cancelsMu.Unlock()
	if ok {
		fn()
	}
	return ok
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

func (q *Queue) Enqueue(ctx context.Context, job DownloadJob) {
	// Serialize trace context onto the job so the worker goroutine can
	// reconstruct the trace parent and emit child spans.
	carrier := make(propagation.MapCarrier)
	otel.GetTextMapPropagator().Inject(ctx, carrier)
	job.TraceCarrier = map[string]string(carrier)

	tracer := otel.Tracer("jobs")
	_, span := tracer.Start(ctx, "job.enqueue",
		trace.WithAttributes(
			attribute.String("job.id", job.ID),
			attribute.String("job.asin", job.AudibleID),
			attribute.String("job.format", job.Format),
		),
	)
	span.End()

	// Seed state with BookID so setStatus preserves it across all subsequent events.
	q.stateMu.Lock()
	q.state[job.ID] = ProgressEvent{JobID: job.ID, BookID: job.BookID}
	q.stateMu.Unlock()

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
