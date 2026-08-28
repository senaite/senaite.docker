package acquire

import (
	"context"
	"sort"
	"sync"

	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/logx"
)

// Manager 按 instrument_code 管理各台仪器的采集连接。
type Manager struct {
	ctx     context.Context
	cfg     func() config.Config
	handler Handler
	log     *logx.Logger

	mu      sync.RWMutex
	clients map[string]*Client
}

// NewManager 构造管理器；ctx 取消时所有仪器连接一并停止。
func NewManager(ctx context.Context, cfg func() config.Config, handler Handler, log *logx.Logger) *Manager {
	return &Manager{
		ctx:     ctx,
		cfg:     cfg,
		handler: handler,
		log:     log,
		clients: map[string]*Client{},
	}
}

func (m *Manager) client(code string) *Client {
	m.mu.Lock()
	defer m.mu.Unlock()
	if c, ok := m.clients[code]; ok {
		return c
	}
	c := newClient(code, m.cfg, m.handler, m.log)
	m.clients[code] = c
	return c
}

// Start 开始采集指定仪器（重复调用同一目标为空操作）。
func (m *Manager) Start(code, host string, port int, push bool) {
	m.client(code).Start(m.ctx, host, port, push)
}

// Stop 停止指定仪器；code 为空时停止全部。
func (m *Manager) Stop(code string) {
	if code != "" {
		m.mu.RLock()
		c, ok := m.clients[code]
		m.mu.RUnlock()
		if ok {
			c.Stop()
		}
		return
	}
	for _, c := range m.all() {
		c.Stop()
	}
}

// Running 返回该仪器是否有采集目标。
func (m *Manager) Running(code string) bool {
	m.mu.RLock()
	c, ok := m.clients[code]
	m.mu.RUnlock()
	if !ok {
		return false
	}
	_, _, running := c.Target()
	return running
}

// Target 返回该仪器当前的采集目标。
func (m *Manager) Target(code string) (host string, port int, ok bool) {
	m.mu.RLock()
	c, exists := m.clients[code]
	m.mu.RUnlock()
	if !exists {
		return "", 0, false
	}
	return c.Target()
}

// States 返回所有仪器的状态，按 code 排序（避免界面表格行乱跳）。
func (m *Manager) States() []Snapshot {
	clients := m.all()
	out := make([]Snapshot, 0, len(clients))
	for _, c := range clients {
		out = append(out, c.Snapshot())
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Code < out[j].Code })
	return out
}

// Snapshot 返回单台仪器状态。
func (m *Manager) Snapshot(code string) (Snapshot, bool) {
	m.mu.RLock()
	c, ok := m.clients[code]
	m.mu.RUnlock()
	if !ok {
		return Snapshot{}, false
	}
	return c.Snapshot(), true
}

func (m *Manager) all() []*Client {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := make([]*Client, 0, len(m.clients))
	for _, c := range m.clients {
		out = append(out, c)
	}
	return out
}

// Close 停止全部采集连接。
func (m *Manager) Close() { m.Stop("") }
