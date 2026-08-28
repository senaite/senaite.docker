package forward_test

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"testing"
	"time"

	"github.com/maitux/labgate/internal/bus"
	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/forward"
	"github.com/maitux/labgate/internal/ingest"
	"github.com/maitux/labgate/internal/logx"
	"github.com/maitux/labgate/internal/model"
	"github.com/maitux/labgate/internal/state"
	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

// freePort 返回一个当前空闲的本地端口。
func freePort(t *testing.T) int {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	return ln.Addr().(*net.TCPAddr).Port
}

// hub 是测试里的"云端 NATS"：开 JetStream（域 hub）与 LeafNode 监听。
type hub struct {
	srv      *server.Server
	leafPort int
	dir      string
}

func startHub(t *testing.T, clientPort, leafPort int, storeDir string) *hub {
	t.Helper()
	srv, err := server.NewServer(&server.Options{
		ServerName:      "test-hub",
		Host:            "127.0.0.1",
		Port:            clientPort,
		JetStream:       true,
		JetStreamDomain: "hub",
		StoreDir:        storeDir,
		NoLog:           true,
		NoSigs:          true,
		LeafNode: server.LeafNodeOpts{
			Host: "127.0.0.1",
			Port: leafPort,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	go srv.Start()
	if !srv.ReadyForConnections(10 * time.Second) {
		t.Fatal("云端 NATS 启动超时")
	}
	return &hub{srv: srv, leafPort: leafPort, dir: storeDir}
}

func (h *hub) stop() {
	h.srv.Shutdown()
	h.srv.WaitForShutdown()
}

// edgeConfig 返回一份指向该 hub 的边缘配置。
func edgeConfig(t *testing.T, leafPort int) config.Config {
	cfg := config.Defaults()
	cfg.Agent.SiteID = "lab-test"
	cfg.Cache.Dir = t.TempDir()
	cfg.NATS.Leaf.Enabled = true
	cfg.NATS.Leaf.URL = fmt.Sprintf("nats-leaf://127.0.0.1:%d", leafPort)
	cfg.NATS.Leaf.EnsureHubStream = true
	cfg.NATS.Leaf.RetryDelaySeconds = 1
	cfg.NATS.Leaf.AckTimeoutSeconds = 3
	return cfg
}

func discardLogger() *logx.Logger { return logx.New(200, slog.New(slog.DiscardHandler)) }

// waitFor 轮询 cond 直到成立或超时。
func waitFor(t *testing.T, timeout time.Duration, cond func() bool) bool {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if cond() {
			return true
		}
		time.Sleep(50 * time.Millisecond)
	}
	return false
}

// hubMessages 统计云端读数流里的消息数。
func hubMessages(t *testing.T, clientPort int, stream string) uint64 {
	t.Helper()
	nc, err := nats.Connect(fmt.Sprintf("nats://127.0.0.1:%d", clientPort))
	if err != nil {
		return 0
	}
	defer nc.Close()
	js, err := jetstream.NewWithDomain(nc, "hub")
	if err != nil {
		return 0
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	s, err := js.Stream(ctx, stream)
	if err != nil {
		return 0
	}
	info, err := s.Info(ctx)
	if err != nil {
		return 0
	}
	return info.State.Msgs
}

// 完整链路：采集 → 边缘 JetStream 落盘 → LeafNode → 云端 JetStream。
func TestReadingReachesHub(t *testing.T) {
	clientPort, leafPort := freePort(t), freePort(t)
	h := startHub(t, clientPort, leafPort, t.TempDir())
	defer h.stop()

	cfg := edgeConfig(t, leafPort)
	log := discardLogger()
	st := state.New(100)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	b, err := bus.Start(ctx, cfg, log)
	if err != nil {
		t.Fatal(err)
	}
	defer b.Close()

	if _, err := b.EnsureLocalStream(ctx); err != nil {
		t.Fatal(err)
	}
	if !waitFor(t, 10*time.Second, b.LeafConnected) {
		t.Fatal("LeafNode 没有连上云端")
	}

	cloud := forward.NewCloud(b, func() config.Config { return cfg }, st, log)
	go cloud.Run(ctx) //nolint:errcheck // 退出原因由 ctx 决定

	ing := ingest.New(b.LocalJS(), func() config.Config { return cfg }, st, log)
	for i := range 3 {
		if _, err := ing.Submit(ctx, "bal-1",
			fmt.Sprintf("ST,GS,0.%03d,mg", i), fmt.Sprintf("0.%03d", i), "mg", true); err != nil {
			t.Fatalf("落盘失败: %v", err)
		}
	}

	if !waitFor(t, 15*time.Second, func() bool {
		return hubMessages(t, clientPort, cfg.NATS.Leaf.HubStream) >= 3
	}) {
		t.Fatalf("读数没有到达云端，云端消息数 = %d",
			hubMessages(t, clientPort, cfg.NATS.Leaf.HubStream))
	}
	if got := st.Stats().PushOK; got < 3 {
		t.Errorf("上传成功计数有误: %d", got)
	}
}

// 断网续传：云端不可用时数据留在本地，云端恢复后自动补齐。
func TestStoreAndForwardAcrossOutage(t *testing.T) {
	clientPort, leafPort := freePort(t), freePort(t)
	hubDir := t.TempDir()

	cfg := edgeConfig(t, leafPort)
	log := discardLogger()
	st := state.New(100)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// 云端此时还没起来
	b, err := bus.Start(ctx, cfg, log)
	if err != nil {
		t.Fatal(err)
	}
	defer b.Close()
	if _, err := b.EnsureLocalStream(ctx); err != nil {
		t.Fatal(err)
	}

	cloud := forward.NewCloud(b, func() config.Config { return cfg }, st, log)
	go cloud.Run(ctx) //nolint:errcheck // 退出原因由 ctx 决定

	// 断网期间采到的读数必须先在本地落盘
	ing := ingest.New(b.LocalJS(), func() config.Config { return cfg }, st, log)
	const offlineCount = 5
	for i := range offlineCount {
		if _, err := ing.Submit(ctx, "bal-1",
			fmt.Sprintf("offline-%d", i), fmt.Sprint(i), "mg", true); err != nil {
			t.Fatalf("云端不可用时落盘失败（这正是不能丢的一步）: %v", err)
		}
	}

	stream, err := b.LocalJS().Stream(ctx, cfg.NATS.Stream)
	if err != nil {
		t.Fatal(err)
	}
	info, err := stream.Info(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if info.State.Msgs != offlineCount {
		t.Fatalf("本地应留存 %d 条，实际 %d 条", offlineCount, info.State.Msgs)
	}
	if hubMessages(t, clientPort, cfg.NATS.Leaf.HubStream) != 0 {
		t.Fatal("云端还没启动，不应该有消息")
	}

	// 云端恢复
	h := startHub(t, clientPort, leafPort, hubDir)
	defer h.stop()

	if !waitFor(t, 20*time.Second, b.LeafConnected) {
		t.Fatal("云端恢复后 LeafNode 没有重连")
	}
	if !waitFor(t, 30*time.Second, func() bool {
		return hubMessages(t, clientPort, cfg.NATS.Leaf.HubStream) >= offlineCount
	}) {
		t.Fatalf("断网期间的数据没有补传，云端只有 %d 条",
			hubMessages(t, clientPort, cfg.NATS.Leaf.HubStream))
	}
}

// 同一 event_id 重复提交只应在云端留下一条（幂等）。
func TestDuplicateEventIDDeduplicated(t *testing.T) {
	clientPort, leafPort := freePort(t), freePort(t)
	h := startHub(t, clientPort, leafPort, t.TempDir())
	defer h.stop()

	cfg := edgeConfig(t, leafPort)
	log := discardLogger()
	st := state.New(100)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	b, err := bus.Start(ctx, cfg, log)
	if err != nil {
		t.Fatal(err)
	}
	defer b.Close()
	if _, err := b.EnsureLocalStream(ctx); err != nil {
		t.Fatal(err)
	}
	if !waitFor(t, 10*time.Second, b.LeafConnected) {
		t.Fatal("LeafNode 没有连上云端")
	}

	cloud := forward.NewCloud(b, func() config.Config { return cfg }, st, log)
	go cloud.Run(ctx) //nolint:errcheck // 退出原因由 ctx 决定

	// 直接用同一个 event_id 发两次
	reading := model.NewReading("agent-fixed-id", cfg.Agent.SiteID, "bal-1", "dup", "1", "mg")
	data, err := reading.Encode()
	if err != nil {
		t.Fatal(err)
	}
	for range 2 {
		if _, err := b.LocalJS().Publish(ctx, cfg.LocalSubject("bal-1"), data,
			jetstream.WithMsgID(reading.EventID)); err != nil {
			t.Fatal(err)
		}
	}

	if !waitFor(t, 15*time.Second, func() bool {
		return hubMessages(t, clientPort, cfg.NATS.Leaf.HubStream) >= 1
	}) {
		t.Fatal("读数没有到达云端")
	}
	time.Sleep(2 * time.Second) // 给第二条留出被去重的时间
	if got := hubMessages(t, clientPort, cfg.NATS.Leaf.HubStream); got != 1 {
		t.Errorf("重复 event_id 应只留一条，云端有 %d 条", got)
	}
}

// 关闭"上传"开关时读数只进界面，不落盘也不上云。
func TestPushDisabledSkipsStream(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	cfg := config.Defaults()
	cfg.Cache.Dir = t.TempDir()
	log := discardLogger()
	st := state.New(100)

	b, err := bus.Start(ctx, cfg, log)
	if err != nil {
		t.Fatal(err)
	}
	defer b.Close()
	if _, err := b.EnsureLocalStream(ctx); err != nil {
		t.Fatal(err)
	}

	ing := ingest.New(b.LocalJS(), func() config.Config { return cfg }, st, log)
	if _, err := ing.Submit(ctx, "bal-1", "local-only", "1", "mg", false); err != nil {
		t.Fatal(err)
	}

	stream, err := b.LocalJS().Stream(ctx, cfg.NATS.Stream)
	if err != nil {
		t.Fatal(err)
	}
	info, err := stream.Info(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if info.State.Msgs != 0 {
		t.Errorf("关闭上传时不应写入流，实际 %d 条", info.State.Msgs)
	}
	if len(st.Readings(10)) != 1 {
		t.Error("关闭上传时界面仍应看到这条读数")
	}
	if st.Stats().PushSkipped != 1 {
		t.Errorf("push_skipped 计数有误: %d", st.Stats().PushSkipped)
	}
}
