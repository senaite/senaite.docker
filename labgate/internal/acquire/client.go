// Package acquire 负责与仪器建立 TCP 连接并按行取出读数。
//
// 一台仪器一个 Client（独立 goroutine 与状态），一台仪器断线不影响其他仪器。
// 断线自动重连；连接持续失败时日志去重，避免刷屏。
package acquire

import (
	"context"
	"errors"
	"fmt"
	"net"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/logx"
	"github.com/maitux/labgate/internal/parse"
)

// Handler 在收到并解析一行读数后被调用。
type Handler func(ctx context.Context, code, raw, value, unit string, push bool)

// Snapshot 是一台仪器的连接状态（供界面与 /api/state 展示）。
type Snapshot struct {
	Code          string `json:"code"`
	Connected     bool   `json:"connected"`
	Connecting    bool   `json:"connecting"`
	LastMessage   string `json:"last_message"`
	CurrentHost   string `json:"current_host"`
	CurrentPort   int    `json:"current_port"`
	TotalReceived int64  `json:"total_received"`
	TotalParsed   int64  `json:"total_parsed"`
}

type target struct {
	host string
	port int
	push bool
}

// Client 是单台仪器的采集连接。
type Client struct {
	code    string
	cfg     func() config.Config
	handler Handler
	log     *logx.Logger

	mu      sync.Mutex
	current *target
	cancel  context.CancelFunc
	done    chan struct{}

	connected     atomic.Bool
	connecting    atomic.Bool
	lastMessage   atomic.Value // string
	totalReceived atomic.Int64
	totalParsed   atomic.Int64
}

func newClient(code string, cfg func() config.Config, handler Handler, log *logx.Logger) *Client {
	c := &Client{code: code, cfg: cfg, handler: handler, log: log}
	c.lastMessage.Store("未连接")
	return c
}

// Start 开始（或切换）采集目标；对同一目标重复调用是空操作。
//
// 空操作这一点很重要：自动模式下每个轮询周期都会调用一次 Start，
// 若不做幂等判断会反复断开重连。
func (c *Client) Start(parent context.Context, host string, port int, push bool) {
	t := &target{host: host, port: port, push: push}
	c.mu.Lock()
	if c.current != nil && *c.current == *t && c.done != nil {
		select {
		case <-c.done: // 上一轮已退出，需要重启
		default:
			c.mu.Unlock()
			return
		}
	}
	c.stopLocked()
	ctx, cancel := context.WithCancel(parent)
	done := make(chan struct{})
	c.current = t
	c.cancel = cancel
	c.done = done
	c.mu.Unlock()

	c.connecting.Store(true)
	c.lastMessage.Store(fmt.Sprintf("正在连接 %s:%d", host, port))
	c.log.Infof("[%s] 开始采集：连接 %s:%d", c.code, host, port)
	go func() {
		defer close(done)
		c.run(ctx, *t)
	}()
}

// Stop 停止采集。
func (c *Client) Stop() {
	c.mu.Lock()
	had := c.current != nil
	c.stopLocked()
	c.mu.Unlock()
	if had {
		c.log.Infof("[%s] 停止采集", c.code)
	}
	c.connected.Store(false)
	c.connecting.Store(false)
	c.lastMessage.Store("已停止采集")
	c.log.ResetDedup("conn:" + c.code)
}

// stopLocked 取消当前会话并等待其退出；调用方须持有 c.mu。
func (c *Client) stopLocked() {
	if c.cancel != nil {
		c.cancel()
	}
	done := c.done
	c.cancel = nil
	c.done = nil
	c.current = nil
	if done != nil {
		select {
		case <-done:
		case <-time.After(3 * time.Second):
			// 收数 goroutine 卡在 syscall 上时不阻塞调用方；
			// ctx 已取消，它随后自行退出。
		}
	}
}

// Target 返回当前采集目标。
func (c *Client) Target() (host string, port int, ok bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.current == nil {
		return "", 0, false
	}
	return c.current.host, c.current.port, true
}

// Snapshot 返回状态快照。
func (c *Client) Snapshot() Snapshot {
	host, port, _ := c.Target()
	msg, _ := c.lastMessage.Load().(string)
	return Snapshot{
		Code:          c.code,
		Connected:     c.connected.Load(),
		Connecting:    c.connecting.Load(),
		LastMessage:   msg,
		CurrentHost:   host,
		CurrentPort:   port,
		TotalReceived: c.totalReceived.Load(),
		TotalParsed:   c.totalParsed.Load(),
	}
}

// run 是采集主循环：连接 → 收数 → 断线重连，直到 ctx 取消。
func (c *Client) run(ctx context.Context, t target) {
	defer func() {
		c.connected.Store(false)
		c.connecting.Store(false)
	}()
	addr := net.JoinHostPort(t.host, fmt.Sprint(t.port))
	dedupKey := "conn:" + c.code

	for ctx.Err() == nil {
		cfg := c.cfg().Instrument
		connectTimeout := time.Duration(config.OrDefaultInt(cfg.ConnectTimeoutSeconds, 3)) * time.Second
		reconnectDelay := time.Duration(config.OrDefaultInt(cfg.ReconnectDelaySeconds, 3)) * time.Second

		c.connecting.Store(true)
		dialer := net.Dialer{Timeout: connectTimeout}
		conn, err := dialer.DialContext(ctx, "tcp", addr)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			c.connected.Store(false)
			c.connecting.Store(false)
			c.lastMessage.Store("连接失败：" + err.Error())
			// 天平未开机时每几秒重试一次，日志去重只在原因变化时记一条
			c.log.Dedupf(dedupKey, logx.LevelWarning,
				"[%s] 连接 %s 失败：%v（持续重试中）", c.code, addr, err)
			if !sleepCtx(ctx, reconnectDelay) {
				return
			}
			continue
		}

		c.connected.Store(true)
		c.connecting.Store(false)
		c.lastMessage.Store(fmt.Sprintf("已连接 %s", addr))
		c.log.ResetDedup(dedupKey)
		c.log.Infof("[%s] 已连接 %s", c.code, addr)

		err = c.readLoop(ctx, conn, t)
		_ = conn.Close()
		c.connected.Store(false)

		if ctx.Err() != nil {
			return
		}
		if err != nil {
			c.lastMessage.Store("连接断开，等待重连：" + err.Error())
			c.log.Warnf("[%s] 连接断开 %s：%v", c.code, addr, err)
		} else {
			c.lastMessage.Store("连接断开，等待重连")
			c.log.Warnf("[%s] 连接断开 %s", c.code, addr)
		}
		if !sleepCtx(ctx, reconnectDelay) {
			return
		}
	}
}

// readLoop 从连接中按行取出读数。
//
// 读超时（idle_flush_milliseconds）有两个作用：一是让 ctx 取消能及时生效，
// 二是把"发过来但没有换行符"的数据在空闲后当作完整一行处理 —— 有些串口
// 服务器和调试工具（NetAssist 手动发送）不带换行。
func (c *Client) readLoop(ctx context.Context, conn net.Conn, t target) error {
	icfg := c.cfg().Instrument
	terminator := icfg.LineTerminator
	if terminator == "" {
		terminator = "\n"
	}
	idle := time.Duration(config.OrDefaultInt(icfg.IdleFlushMilliseconds, 500)) * time.Millisecond
	maxLine := config.OrDefaultInt(icfg.MaxLineBytes, 64*1024)

	buf := make([]byte, 4096)
	var pending strings.Builder

	for {
		if ctx.Err() != nil {
			return nil
		}
		if err := conn.SetReadDeadline(time.Now().Add(idle)); err != nil {
			return err
		}
		n, err := conn.Read(buf)
		if n > 0 {
			pending.Write(buf[:n])
			// 防御：对端一直不发换行符时不让缓冲无限增长
			if pending.Len() > maxLine {
				c.log.Warnf("[%s] 单行超过 %d 字节，已按整行处理", c.code, maxLine)
				c.emit(ctx, pending.String(), t)
				pending.Reset()
			}
			rest := c.emitLines(ctx, pending.String(), terminator, t)
			pending.Reset()
			pending.WriteString(rest)
		}
		if err != nil {
			var nerr net.Error
			if errors.As(err, &nerr) && nerr.Timeout() {
				// 空闲：把没有换行符的残留当作完整一行
				if strings.TrimSpace(pending.String()) != "" {
					c.emit(ctx, pending.String(), t)
					pending.Reset()
				}
				continue
			}
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		if n == 0 {
			return errors.New("对端关闭连接")
		}
	}
}

// emitLines 处理已成行的部分，返回尚未成行的残留。
func (c *Client) emitLines(ctx context.Context, data, terminator string, t target) string {
	parts := strings.Split(data, terminator)
	rest := parts[len(parts)-1]
	for _, line := range parts[:len(parts)-1] {
		c.emit(ctx, line, t)
	}
	return rest
}

func (c *Client) emit(ctx context.Context, line string, t target) {
	line = strings.TrimSpace(strings.Trim(line, "\r"))
	if line == "" {
		return
	}
	value, unit := parse.Reading(line)
	c.totalReceived.Add(1)
	if value != "" {
		c.totalParsed.Add(1)
	}
	if c.handler != nil {
		c.handler(ctx, c.code, line, value, unit, t.push)
	}
}

// sleepCtx 睡眠 d，若 ctx 先取消则返回 false。
func sleepCtx(ctx context.Context, d time.Duration) bool {
	if d <= 0 {
		return ctx.Err() == nil
	}
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}
