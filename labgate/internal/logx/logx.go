// Package logx 提供既写标准输出、又写内存环形缓冲的运行日志。
//
// 环形缓冲供界面「日志」页与 /api/logs 读取，容量固定，不落盘、不增长。
package logx

import (
	"fmt"
	"log/slog"
	"sync"
	"time"
)

// 日志级别（与旧采集端 /api/logs 返回值一致，界面按此着色）。
const (
	LevelInfo    = "info"
	LevelWarning = "warning"
	LevelError   = "error"
)

// Entry 是一条界面可见的运行日志。
type Entry struct {
	Time    string `json:"time"`
	Level   string `json:"level"`
	Message string `json:"message"`
}

// Logger 是带环形缓冲的日志器。零值不可用，请用 New 构造。
type Logger struct {
	mu    sync.Mutex
	buf   []Entry
	next  int
	full  bool
	slog  *slog.Logger
	dedup map[string]string // key -> 上次消息，用于抑制重复刷屏
}

// New 构造一个容量为 capacity 的日志器。
func New(capacity int, base *slog.Logger) *Logger {
	if capacity <= 0 {
		capacity = 500
	}
	if base == nil {
		base = slog.Default()
	}
	return &Logger{
		buf:   make([]Entry, capacity),
		slog:  base,
		dedup: map[string]string{},
	}
}

// Infof 记录一条 info 日志。
func (l *Logger) Infof(format string, args ...any) {
	l.log(LevelInfo, fmt.Sprintf(format, args...))
}

// Warnf 记录一条 warning 日志。
func (l *Logger) Warnf(format string, args ...any) {
	l.log(LevelWarning, fmt.Sprintf(format, args...))
}

// Errorf 记录一条 error 日志。
func (l *Logger) Errorf(format string, args ...any) {
	l.log(LevelError, fmt.Sprintf(format, args...))
}

// Dedupf 只在消息相对上次同 key 的消息发生变化时才记录。
//
// 用于仪器持续连接失败一类场景：天平未开机时每几秒重试一次，
// 每次都记日志会把日志页刷满，这里只在状态变化时记一条。
func (l *Logger) Dedupf(key, level, format string, args ...any) {
	msg := fmt.Sprintf(format, args...)
	l.mu.Lock()
	last, ok := l.dedup[key]
	if ok && last == msg {
		l.mu.Unlock()
		return
	}
	l.dedup[key] = msg
	l.mu.Unlock()
	l.log(level, msg)
}

// ResetDedup 清除某个 key 的去重状态，使下一条同样的消息能重新记录。
func (l *Logger) ResetDedup(key string) {
	l.mu.Lock()
	delete(l.dedup, key)
	l.mu.Unlock()
}

func (l *Logger) log(level, msg string) {
	entry := Entry{
		Time:    time.Now().Format("2006-01-02 15:04:05"),
		Level:   level,
		Message: msg,
	}
	l.mu.Lock()
	l.buf[l.next] = entry
	l.next = (l.next + 1) % len(l.buf)
	if l.next == 0 {
		l.full = true
	}
	l.mu.Unlock()

	switch level {
	case LevelError:
		l.slog.Error(msg)
	case LevelWarning:
		l.slog.Warn(msg)
	default:
		l.slog.Info(msg)
	}
}

// Snapshot 返回最近 limit 条日志，最新的在前。
func (l *Logger) Snapshot(limit int) []Entry {
	l.mu.Lock()
	defer l.mu.Unlock()
	n := len(l.buf)
	count := l.next
	if l.full {
		count = n
	}
	if limit <= 0 || limit > count {
		limit = count
	}
	out := make([]Entry, 0, limit)
	for i := 0; i < limit; i++ {
		idx := (l.next - 1 - i + n*2) % n
		out = append(out, l.buf[idx])
	}
	return out
}
