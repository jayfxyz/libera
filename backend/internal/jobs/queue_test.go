package jobs

import (
	"context"
	"testing"
)

func TestQueue_Cancel_NonExistent(t *testing.T) {
	q := &Queue{cancels: map[string]context.CancelFunc{}}
	// Cancelling a job that was never registered must not panic and returns false.
	if got := q.Cancel("no-such-job"); got {
		t.Error("expected false for unknown job, got true")
	}
}

func TestQueue_Cancel_RegisteredJob(t *testing.T) {
	q := &Queue{cancels: map[string]context.CancelFunc{}}
	ctx, cancel := context.WithCancel(context.Background())
	q.registerCancel("job-1", cancel)

	if got := q.Cancel("job-1"); !got {
		t.Error("expected true for registered job, got false")
	}
	// The cancel func must have been called — the context should be done.
	if ctx.Err() == nil {
		t.Error("expected context to be cancelled after Cancel()")
	}
	// Second cancel call on same ID must return false (already deregistered).
	if got := q.Cancel("job-1"); got {
		t.Error("expected false for already-cancelled job, got true")
	}
}
