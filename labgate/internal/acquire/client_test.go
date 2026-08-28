package acquire

import (
	"context"
	"log/slog"
	"net"
	"sync"
	"testing"
	"time"

	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/logx"
)

// collector 收集回调里拿到的读数。
type collector struct {
	mu    sync.Mutex
	lines []string
	value []string
}

func (c *collector) handler(_ context.Context, _, raw, value, _ string, _ bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lines = append(c.lines, raw)
	c.value = append(c.value, value)
}

func (c *collector) snapshot() []string {
	c.mu.Lock()
	defer c.mu.Unlock()
	return append([]string(nil), c.lines...)
}

func testConfig() func() config.Config {
	cfg := config.Defaults()
	cfg.Instrument.ConnectTimeoutSeconds = 1
	cfg.Instrument.ReconnectDelaySeconds = 1
	cfg.Instrument.IdleFlushMilliseconds = 80
	return func() config.Config { return cfg }
}

func testLogger() *logx.Logger {
	return logx.New(100, slog.New(slog.DiscardHandler))
}

// fakeInstrument 起一个 TCP 服务，把 script 里的内容依次发给客户端。
func fakeInstrument(t *testing.T, onConn func(net.Conn)) (host string, port int, stop func()) {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	go func() {
		defer close(done)
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			go func() {
				defer conn.Close()
				onConn(conn)
			}()
		}
	}()
	addr := ln.Addr().(*net.TCPAddr)
	return "127.0.0.1", addr.Port, func() { ln.Close(); <-done }
}

// waitFor 轮询 cond 直到成立或超时。
func waitFor(t *testing.T, timeout time.Duration, cond func() bool) bool {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if cond() {
			return true
		}
		time.Sleep(10 * time.Millisecond)
	}
	return false
}

// 按换行符分行是最常见的情况。
func TestReadLinesTerminated(t *testing.T) {
	host, port, stop := fakeInstrument(t, func(conn net.Conn) {
		conn.Write([]byte("ST,GS,0.9678,mg\r\nST,GS,1.2345,mg\r\n"))
		time.Sleep(500 * time.Millisecond)
	})
	defer stop()

	c := &collector{}
	client := newClient("bal-1", testConfig(), c.handler, testLogger())
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	client.Start(ctx, host, port, true)
	defer client.Stop()

	if !waitFor(t, 3*time.Second, func() bool { return len(c.snapshot()) >= 2 }) {
		t.Fatalf("没有收到两行读数，实际收到 %v", c.snapshot())
	}
	got := c.snapshot()
	if got[0] != "ST,GS,0.9678,mg" || got[1] != "ST,GS,1.2345,mg" {
		t.Errorf("行内容有误: %v", got)
	}
	if snap := client.Snapshot(); snap.TotalParsed != 2 {
		t.Errorf("解析计数有误: %+v", snap)
	}
}

// 有些串口服务器和调试工具不发换行符，空闲后应把残留当作一整行。
func TestIdleFlushWithoutTerminator(t *testing.T) {
	host, port, stop := fakeInstrument(t, func(conn net.Conn) {
		conn.Write([]byte("0.9678 mg")) // 没有换行符
		time.Sleep(500 * time.Millisecond)
	})
	defer stop()

	c := &collector{}
	client := newClient("bal-1", testConfig(), c.handler, testLogger())
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	client.Start(ctx, host, port, true)
	defer client.Stop()

	if !waitFor(t, 3*time.Second, func() bool { return len(c.snapshot()) >= 1 }) {
		t.Fatal("空闲后没有把无换行的数据成行")
	}
	if got := c.snapshot()[0]; got != "0.9678 mg" {
		t.Errorf("成行内容有误: %q", got)
	}
}

// 分片到达的一行必须拼接完整，不能被拆成两条。
func TestPartialWritesAreJoined(t *testing.T) {
	host, port, stop := fakeInstrument(t, func(conn net.Conn) {
		conn.Write([]byte("ST,GS,0."))
		time.Sleep(20 * time.Millisecond) // 短于 idle_flush，不应触发成行
		conn.Write([]byte("9678,mg\n"))
		time.Sleep(500 * time.Millisecond)
	})
	defer stop()

	c := &collector{}
	client := newClient("bal-1", testConfig(), c.handler, testLogger())
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	client.Start(ctx, host, port, true)
	defer client.Stop()

	if !waitFor(t, 3*time.Second, func() bool { return len(c.snapshot()) >= 1 }) {
		t.Fatal("没有收到读数")
	}
	if got := c.snapshot()[0]; got != "ST,GS,0.9678,mg" {
		t.Errorf("分片没有正确拼接: %q", got)
	}
}

// 仪器断开后应自动重连并继续收数。
func TestReconnectAfterDisconnect(t *testing.T) {
	var conns int
	var mu sync.Mutex
	host, port, stop := fakeInstrument(t, func(conn net.Conn) {
		mu.Lock()
		conns++
		n := conns
		mu.Unlock()
		if n == 1 {
			conn.Write([]byte("first\n"))
			return // 立即断开，触发重连
		}
		conn.Write([]byte("second\n"))
		time.Sleep(time.Second)
	})
	defer stop()

	c := &collector{}
	client := newClient("bal-1", testConfig(), c.handler, testLogger())
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	client.Start(ctx, host, port, true)
	defer client.Stop()

	if !waitFor(t, 6*time.Second, func() bool { return len(c.snapshot()) >= 2 }) {
		t.Fatalf("断线后没有重连并继续收数，实际收到 %v", c.snapshot())
	}
	got := c.snapshot()
	if got[0] != "first" || got[1] != "second" {
		t.Errorf("重连后的数据有误: %v", got)
	}
}

// 对同一目标重复调用 Start 不应断开重连
// —— 自动模式下每个轮询周期都会调一次。
func TestStartIsIdempotent(t *testing.T) {
	var conns int
	var mu sync.Mutex
	host, port, stop := fakeInstrument(t, func(conn net.Conn) {
		mu.Lock()
		conns++
		mu.Unlock()
		time.Sleep(2 * time.Second)
	})
	defer stop()

	c := &collector{}
	client := newClient("bal-1", testConfig(), c.handler, testLogger())
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	client.Start(ctx, host, port, true)
	if !waitFor(t, 3*time.Second, func() bool { return client.Snapshot().Connected }) {
		t.Fatal("首次连接失败")
	}
	for range 5 {
		client.Start(ctx, host, port, true)
	}
	time.Sleep(200 * time.Millisecond)
	client.Stop()

	mu.Lock()
	defer mu.Unlock()
	if conns != 1 {
		t.Errorf("重复 Start 造成了 %d 次连接，应该只有 1 次", conns)
	}
}

// 换目标地址时应断开旧连接、连到新地址。
func TestStartSwitchesTarget(t *testing.T) {
	hostA, portA, stopA := fakeInstrument(t, func(conn net.Conn) {
		conn.Write([]byte("from-a\n"))
		time.Sleep(2 * time.Second)
	})
	defer stopA()
	hostB, portB, stopB := fakeInstrument(t, func(conn net.Conn) {
		conn.Write([]byte("from-b\n"))
		time.Sleep(2 * time.Second)
	})
	defer stopB()

	c := &collector{}
	client := newClient("bal-1", testConfig(), c.handler, testLogger())
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	client.Start(ctx, hostA, portA, true)
	if !waitFor(t, 3*time.Second, func() bool { return len(c.snapshot()) >= 1 }) {
		t.Fatal("没有收到 A 的数据")
	}
	client.Start(ctx, hostB, portB, true)
	if !waitFor(t, 3*time.Second, func() bool { return len(c.snapshot()) >= 2 }) {
		t.Fatalf("切换地址后没有收到 B 的数据，实际 %v", c.snapshot())
	}
	defer client.Stop()

	got := c.snapshot()
	if got[0] != "from-a" || got[1] != "from-b" {
		t.Errorf("切换目标后的数据有误: %v", got)
	}
	if _, p, ok := client.Target(); !ok || p != portB {
		t.Errorf("当前目标应为 B 的端口 %d", portB)
	}
}

// Stop 之后不应再产生读数。
func TestStopEndsAcquisition(t *testing.T) {
	host, port, stop := fakeInstrument(t, func(conn net.Conn) {
		for range 100 {
			if _, err := conn.Write([]byte("tick\n")); err != nil {
				return
			}
			time.Sleep(30 * time.Millisecond)
		}
	})
	defer stop()

	c := &collector{}
	client := newClient("bal-1", testConfig(), c.handler, testLogger())
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	client.Start(ctx, host, port, true)
	if !waitFor(t, 3*time.Second, func() bool { return len(c.snapshot()) >= 2 }) {
		t.Fatal("没有收到数据")
	}
	client.Stop()
	time.Sleep(150 * time.Millisecond)
	before := len(c.snapshot())
	time.Sleep(300 * time.Millisecond)

	if after := len(c.snapshot()); after != before {
		t.Errorf("Stop 之后仍在收数：%d → %d", before, after)
	}
	if snap := client.Snapshot(); snap.Connected {
		t.Error("Stop 之后 connected 仍为 true")
	}
}

// 连不上时应持续重试，并把原因写进状态而不是刷屏。
func TestConnectFailureRetries(t *testing.T) {
	// 占一个端口再立刻释放，得到一个大概率无人监听的地址
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := ln.Addr().(*net.TCPAddr).Port
	ln.Close()

	c := &collector{}
	client := newClient("bal-1", testConfig(), c.handler, testLogger())
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	client.Start(ctx, "127.0.0.1", port, true)
	defer client.Stop()

	ok := waitFor(t, 3*time.Second, func() bool {
		snap := client.Snapshot()
		return !snap.Connected && snap.LastMessage != "" &&
			snap.LastMessage != "未连接"
	})
	if !ok {
		t.Errorf("连接失败没有反映到状态：%+v", client.Snapshot())
	}
}

// Manager 应按 code 隔离各台仪器，一台停止不影响另一台。
func TestManagerIsolatesInstruments(t *testing.T) {
	hostA, portA, stopA := fakeInstrument(t, func(conn net.Conn) {
		conn.Write([]byte("a\n"))
		time.Sleep(2 * time.Second)
	})
	defer stopA()
	hostB, portB, stopB := fakeInstrument(t, func(conn net.Conn) {
		conn.Write([]byte("b\n"))
		time.Sleep(2 * time.Second)
	})
	defer stopB()

	c := &collector{}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	mgr := NewManager(ctx, testConfig(), c.handler, testLogger())
	defer mgr.Close()

	mgr.Start("bal-a", hostA, portA, true)
	mgr.Start("bal-b", hostB, portB, true)

	if !waitFor(t, 3*time.Second, func() bool { return len(mgr.States()) == 2 }) {
		t.Fatal("两台仪器没有都登记")
	}
	if !waitFor(t, 3*time.Second, func() bool {
		return mgr.Running("bal-a") && mgr.Running("bal-b")
	}) {
		t.Fatal("两台仪器没有都在采集")
	}

	mgr.Stop("bal-a")
	if mgr.Running("bal-a") {
		t.Error("bal-a 应已停止")
	}
	if !mgr.Running("bal-b") {
		t.Error("停止 bal-a 不应影响 bal-b")
	}

	// States 按 code 排序，界面表格才不会乱跳
	states := mgr.States()
	if states[0].Code != "bal-a" || states[1].Code != "bal-b" {
		t.Errorf("States 没有按 code 排序: %+v", states)
	}
}
