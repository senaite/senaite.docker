package bridge

import (
	"sync"
	"sync/atomic"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

// worker 是一台仪器正在进行的投递。
type worker struct {
	code     string
	consume  jetstream.ConsumeContext
	consumer jetstream.Consumer

	forwarded atomic.Int64
	skipped   atomic.Int64

	mu          sync.Mutex
	lastError   string
	lastForward string
}

func (w *worker) markForwarded() {
	w.forwarded.Add(1)
	w.mu.Lock()
	w.lastForward = time.Now().Format("2006-01-02 15:04:05")
	w.lastError = ""
	w.mu.Unlock()
}

func (w *worker) markSkipped(reason string) {
	w.skipped.Add(1)
	w.setError(reason)
}

func (w *worker) setError(msg string) {
	w.mu.Lock()
	w.lastError = msg
	w.mu.Unlock()
}

func (w *worker) snapshot() (forwarded, skipped int64, lastError, lastForward string) {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.forwarded.Load(), w.skipped.Load(), w.lastError, w.lastForward
}

func (w *worker) close() {
	if w.consume != nil {
		w.consume.Stop()
	}
}
