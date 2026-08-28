// Package state 保存采集端的运行时状态：统计计数、最近读数、云同步结果。
//
// 这些数据只服务于界面与 /api/* 查询，全部在内存中；真正需要不丢的读数
// 由 JetStream 负责持久化。
package state

import (
	"sync"
	"sync/atomic"
	"time"
)

// ReadingRow 是界面「实时数据」表里的一行。
type ReadingRow struct {
	Seq    int64  `json:"seq"`
	Time   string `json:"time"`
	Code   string `json:"code"`
	Raw    string `json:"raw"`
	Value  string `json:"value"`
	Unit   string `json:"unit"`
	Status string `json:"status"`
}

// Stats 是界面「状态」页的统计块。
//
// 字段名沿用旧采集端，其中：
//   - push_ok / push_fail 现在统计的是「转发到云端 NATS 成功 / 失败」
//   - cache_pending 是 JetStream 中尚未转发上云的消息数
type Stats struct {
	TotalReceived int64 `json:"total_received"`
	TotalParsed   int64 `json:"total_parsed"`
	PushOK        int64 `json:"push_ok"`
	PushFail      int64 `json:"push_fail"`
	PushSkipped   int64 `json:"push_skipped"`
	CachePending  int64 `json:"cache_pending"`
}

// CloudStatus 描述与云端的连通情况。
type CloudStatus struct {
	LeafEnabled   bool   `json:"leaf_enabled"`
	LeafConnected bool   `json:"leaf_connected"`
	LeafURL       string `json:"leaf_url"`
	HubStream     string `json:"hub_stream"`
	LastError     string `json:"last_error"`
	LastForwardAt string `json:"last_forward_at"`
	Pending       int64  `json:"pending"`
	Forwarded     int64  `json:"forwarded"`
	Failed        int64  `json:"failed"`
}

// State 是全局运行时状态（并发安全）。
type State struct {
	mode atomic.Value // string

	totalReceived atomic.Int64
	totalParsed   atomic.Int64
	pushOK        atomic.Int64
	pushFail      atomic.Int64
	pushSkipped   atomic.Int64
	cachePending  atomic.Int64

	seq atomic.Int64

	mu     sync.RWMutex
	recent []ReadingRow // 环形缓冲
	next   int
	full   bool

	cloudMu        sync.RWMutex
	cloudLastPull  map[string]any
	cloudLastError string
	leafConnected  bool
	leafLastError  string
	lastForwardAt  string
}

// New 构造状态容器，最近读数保留 capacity 条。
func New(capacity int) *State {
	if capacity <= 0 {
		capacity = 500
	}
	s := &State{recent: make([]ReadingRow, capacity)}
	s.mode.Store("auto")
	s.cloudLastPull = map[string]any{}
	return s
}

// SetMode 记录当前运行模式（auto / manual）。
func (s *State) SetMode(mode string) { s.mode.Store(mode) }

// Mode 返回当前运行模式。
func (s *State) Mode() string {
	if v, ok := s.mode.Load().(string); ok {
		return v
	}
	return "auto"
}

// AddReading 记录一条新读数，返回其序号。
func (s *State) AddReading(code, raw, value, unit, status string) int64 {
	seq := s.seq.Add(1)
	s.totalReceived.Add(1)
	if value != "" {
		s.totalParsed.Add(1)
	}
	row := ReadingRow{
		Seq:    seq,
		Time:   time.Now().Format("15:04:05"),
		Code:   code,
		Raw:    raw,
		Value:  value,
		Unit:   unit,
		Status: status,
	}
	s.mu.Lock()
	s.recent[s.next] = row
	s.next = (s.next + 1) % len(s.recent)
	if s.next == 0 {
		s.full = true
	}
	s.mu.Unlock()
	return seq
}

// Readings 返回最近 limit 条读数，最新的在前。
func (s *State) Readings(limit int) []ReadingRow {
	s.mu.RLock()
	defer s.mu.RUnlock()
	n := len(s.recent)
	count := s.next
	if s.full {
		count = n
	}
	if limit <= 0 || limit > count {
		limit = count
	}
	out := make([]ReadingRow, 0, limit)
	for i := 0; i < limit; i++ {
		out = append(out, s.recent[(s.next-1-i+n*2)%n])
	}
	return out
}

// 计数器操作。
func (s *State) IncPushOK()         { s.pushOK.Add(1) }
func (s *State) IncPushFail()       { s.pushFail.Add(1) }
func (s *State) IncPushSkipped()    { s.pushSkipped.Add(1) }
func (s *State) SetPending(n int64) { s.cachePending.Store(n) }
func (s *State) Pending() int64     { return s.cachePending.Load() }

// Stats 返回统计快照。
func (s *State) Stats() Stats {
	return Stats{
		TotalReceived: s.totalReceived.Load(),
		TotalParsed:   s.totalParsed.Load(),
		PushOK:        s.pushOK.Load(),
		PushFail:      s.pushFail.Load(),
		PushSkipped:   s.pushSkipped.Load(),
		CachePending:  s.cachePending.Load(),
	}
}

// SetCloudPull 记录一次云 LIMS 轮询结果（自动模式，界面「状态」页展示）。
func (s *State) SetCloudPull(result map[string]any, err string) {
	s.cloudMu.Lock()
	defer s.cloudMu.Unlock()
	if result != nil {
		s.cloudLastPull = result
	}
	s.cloudLastError = err
}

// CloudPull 返回最近一次云 LIMS 轮询结果与错误。
func (s *State) CloudPull() (map[string]any, string) {
	s.cloudMu.RLock()
	defer s.cloudMu.RUnlock()
	out := make(map[string]any, len(s.cloudLastPull))
	for k, v := range s.cloudLastPull {
		out[k] = v
	}
	return out, s.cloudLastError
}

// SetLeaf 记录 LeafNode 连接状态与最近一次转发错误。
func (s *State) SetLeaf(connected bool, lastErr string) {
	s.cloudMu.Lock()
	defer s.cloudMu.Unlock()
	s.leafConnected = connected
	s.leafLastError = lastErr
}

// SetLeafConnected 只更新连接状态，保留已记录的错误原因。
func (s *State) SetLeafConnected(connected bool) {
	s.cloudMu.Lock()
	defer s.cloudMu.Unlock()
	s.leafConnected = connected
}

// MarkForwarded 记录一次成功上云的时间。
func (s *State) MarkForwarded() {
	s.cloudMu.Lock()
	s.lastForwardAt = time.Now().Format("2006-01-02 15:04:05")
	s.cloudMu.Unlock()
}

// Leaf 返回 LeafNode 连接状态、最近错误与最近成功转发时间。
func (s *State) Leaf() (connected bool, lastErr, lastForwardAt string) {
	s.cloudMu.RLock()
	defer s.cloudMu.RUnlock()
	return s.leafConnected, s.leafLastError, s.lastForwardAt
}
