package bridge_test

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/maitux/labgate/internal/bridge"
	"github.com/maitux/labgate/internal/limsapi"
	"github.com/maitux/labgate/internal/logx"
	"github.com/maitux/labgate/internal/model"
	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

// ---------------------------------------------------------------------------
// 假的 SENAITE：只实现桥接层用到的两个接口，行为与真插件一致
//
//	没有监听中的会话   → ingest 返回 404 rejected
//	event_id 已见过     → 200 duplicate
//	正常                → 200 created

type fakeLIMS struct {
	srv *httptest.Server

	mu         sync.Mutex
	listening  map[string]bool
	received   []model.Reading
	seen       map[string]bool
	ingestHits int
}

func newFakeLIMS(t *testing.T) *fakeLIMS {
	t.Helper()
	f := &fakeLIMS{
		listening: map[string]bool{},
		seen:      map[string]bool{},
	}
	mux := http.NewServeMux()

	mux.HandleFunc(limsapi.InstrumentsPath, func(w http.ResponseWriter, r *http.Request) {
		f.mu.Lock()
		list := make([]limsapi.Instruction, 0, len(f.listening))
		for code, on := range f.listening {
			list = append(list, limsapi.Instruction{Code: code, Start: on, IP: "1.2.3.4", Port: 9000})
		}
		f.mu.Unlock()
		writeJSON(w, 200, map[string]any{"instruments": list})
	})

	mux.HandleFunc(limsapi.IngestPath, func(w http.ResponseWriter, r *http.Request) {
		var reading model.Reading
		if err := json.NewDecoder(r.Body).Decode(&reading); err != nil {
			writeJSON(w, 400, map[string]any{"success": false, "status": "rejected"})
			return
		}
		f.mu.Lock()
		defer f.mu.Unlock()
		f.ingestHits++

		if !f.listening[reading.InstrumentCode] {
			writeJSON(w, 404, map[string]any{
				"success": false, "status": "rejected",
				"message": "No active listening session for instrument_code " + reading.InstrumentCode,
			})
			return
		}
		if f.seen[reading.EventID] {
			writeJSON(w, 200, map[string]any{"success": true, "status": "duplicate"})
			return
		}
		f.seen[reading.EventID] = true
		f.received = append(f.received, reading)
		writeJSON(w, 200, map[string]any{"success": true, "status": "created"})
	})

	f.srv = httptest.NewServer(mux)
	t.Cleanup(f.srv.Close)
	return f
}

func (f *fakeLIMS) setListening(code string, on bool) {
	f.mu.Lock()
	f.listening[code] = on
	f.mu.Unlock()
}

func (f *fakeLIMS) raw() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]string, 0, len(f.received))
	for _, r := range f.received {
		out = append(out, r.RawText)
	}
	return out
}

func (f *fakeLIMS) count() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.received)
}

func (f *fakeLIMS) hits() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.ingestHits
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

// ---------------------------------------------------------------------------
// 测试用的云端 NATS + LAB_READINGS 流

const testStream = "LAB_READINGS"

func startHub(t *testing.T) jetstream.JetStream {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := ln.Addr().(*net.TCPAddr).Port
	ln.Close()

	srv, err := server.NewServer(&server.Options{
		ServerName: "test-hub", Host: "127.0.0.1", Port: port,
		JetStream: true, StoreDir: t.TempDir(), NoLog: true, NoSigs: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	go srv.Start()
	if !srv.ReadyForConnections(10 * time.Second) {
		t.Fatal("云端 NATS 启动超时")
	}
	t.Cleanup(func() { srv.Shutdown(); srv.WaitForShutdown() })

	nc, err := nats.Connect(fmt.Sprintf("nats://127.0.0.1:%d", port))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(nc.Close)

	js, err := jetstream.New(nc)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if _, err := js.CreateOrUpdateStream(ctx, jetstream.StreamConfig{
		Name:       testStream,
		Subjects:   []string{"lab.>"},
		Storage:    jetstream.FileStorage,
		Duplicates: 5 * time.Minute,
	}); err != nil {
		t.Fatal(err)
	}
	return js
}

// publish 往云端流里写一条读数，模拟某个实验室的 labgate 传上来的数据。
func publish(t *testing.T, js jetstream.JetStream, code, raw string) {
	t.Helper()
	reading := model.NewReading("agent-"+raw, "lab-test", code, raw, "1", "mg")
	data, err := reading.Encode()
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if _, err := js.Publish(ctx, "lab.lab-test.readings."+code, data,
		jetstream.WithMsgID(reading.EventID)); err != nil {
		t.Fatal(err)
	}
}

func runBridge(t *testing.T, js jetstream.JetStream, f *fakeLIMS, lookback time.Duration) {
	t.Helper()
	log := logx.New(200, slog.New(slog.DiscardHandler))
	b := bridge.New(js, limsapi.New(f.srv.URL, "token", 5*time.Second), bridge.Options{
		Stream:        testStream,
		SubjectPrefix: "lab",
		Lookback:      lookback,
		PollInterval:  200 * time.Millisecond,
		RetryDelay:    200 * time.Millisecond,
	}, log)

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() { defer close(done); b.Run(ctx) }() //nolint:errcheck // 退出原因由 ctx 决定
	t.Cleanup(func() { cancel(); <-done })
}

func waitFor(t *testing.T, timeout time.Duration, cond func() bool) bool {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if cond() {
			return true
		}
		time.Sleep(25 * time.Millisecond)
	}
	return false
}

// ---------------------------------------------------------------------------

// 核心场景：技术员先称量、后在 LIMS 点「开始采集」，之前的读数也要归进去。
func TestReplaysReadingsTakenBeforeSessionOpened(t *testing.T) {
	js := startHub(t)
	f := newFakeLIMS(t)
	f.setListening("bal-1", false)

	// 会话还没开，天平已经在出数
	publish(t, js, "bal-1", "before-1")
	publish(t, js, "bal-1", "before-2")
	publish(t, js, "bal-1", "before-3")

	runBridge(t, js, f, time.Hour)

	// 没有会话时一条都不该投进去
	time.Sleep(700 * time.Millisecond)
	if got := f.count(); got != 0 {
		t.Fatalf("没有监听会话时不该投递，LIMS 却收到 %d 条", got)
	}

	// 技术员点了「开始采集」
	f.setListening("bal-1", true)

	if !waitFor(t, 10*time.Second, func() bool { return f.count() >= 3 }) {
		t.Fatalf("会话开启后没有补投之前的读数，只收到 %v", f.raw())
	}
	got := f.raw()
	for _, want := range []string{"before-1", "before-2", "before-3"} {
		if !contains(got, want) {
			t.Errorf("缺少会话开始前的读数 %q，实际收到 %v", want, got)
		}
	}

	// 会话开启后的新读数也要继续投
	publish(t, js, "bal-1", "after-1")
	if !waitFor(t, 10*time.Second, func() bool { return contains(f.raw(), "after-1") }) {
		t.Errorf("会话开启后的新读数没有投递，实际收到 %v", f.raw())
	}
}

// 超出回溯窗口的陈年读数不该被补投
// —— 否则周一开会话时会把上周的漂移读数全灌进 LIMS。
func TestDoesNotReplayBeyondLookback(t *testing.T) {
	js := startHub(t)
	f := newFakeLIMS(t)
	f.setListening("bal-1", false)

	publish(t, js, "bal-1", "ancient")
	// 让这条读数"变老"，超出下面设的回溯窗口
	time.Sleep(600 * time.Millisecond)

	runBridge(t, js, f, 200*time.Millisecond)
	f.setListening("bal-1", true)

	// 新读数应该能进，证明桥接确实在工作
	publish(t, js, "bal-1", "fresh")
	if !waitFor(t, 10*time.Second, func() bool { return contains(f.raw(), "fresh") }) {
		t.Fatalf("新读数没有投递，实际收到 %v", f.raw())
	}
	if contains(f.raw(), "ancient") {
		t.Errorf("超出回溯窗口的陈年读数不该补投，实际收到 %v", f.raw())
	}
}

// 会话关闭期间的读数留在流里，下次开会话继续投，一条不丢。
func TestResumesAfterSessionCloses(t *testing.T) {
	js := startHub(t)
	f := newFakeLIMS(t)
	f.setListening("bal-1", true)
	runBridge(t, js, f, time.Hour)

	publish(t, js, "bal-1", "session-1")
	if !waitFor(t, 10*time.Second, func() bool { return contains(f.raw(), "session-1") }) {
		t.Fatalf("第一次会话期间的读数没投递，实际 %v", f.raw())
	}

	// 会话关闭，天平还在出数
	f.setListening("bal-1", false)
	time.Sleep(500 * time.Millisecond)
	publish(t, js, "bal-1", "between-1")
	publish(t, js, "bal-1", "between-2")
	time.Sleep(700 * time.Millisecond)
	if contains(f.raw(), "between-1") {
		t.Fatal("会话关闭期间不该投递")
	}

	// 第二次会话
	f.setListening("bal-1", true)
	if !waitFor(t, 10*time.Second, func() bool {
		return contains(f.raw(), "between-1") && contains(f.raw(), "between-2")
	}) {
		t.Errorf("第二次会话没有补投期间的读数，实际收到 %v", f.raw())
	}
}

// 一台仪器没有会话，不能拖住另一台的投递。
func TestInstrumentsAreIsolated(t *testing.T) {
	js := startHub(t)
	f := newFakeLIMS(t)
	f.setListening("bal-1", false)
	f.setListening("bal-2", true)
	runBridge(t, js, f, time.Hour)

	for i := range 5 {
		publish(t, js, "bal-1", fmt.Sprintf("blocked-%d", i))
	}
	publish(t, js, "bal-2", "flowing-1")

	if !waitFor(t, 10*time.Second, func() bool { return contains(f.raw(), "flowing-1") }) {
		t.Fatalf("bal-1 没有会话，却拖住了 bal-2 的投递，实际收到 %v", f.raw())
	}
	if f.count() != 1 {
		t.Errorf("只应投递 bal-2 的读数，实际收到 %v", f.raw())
	}
}

// 重复投递不该在 LIMS 里留下两条 —— 靠 event_id 幂等。
func TestDuplicatesAreDeduplicated(t *testing.T) {
	js := startHub(t)
	f := newFakeLIMS(t)
	f.setListening("bal-1", true)
	runBridge(t, js, f, time.Hour)

	publish(t, js, "bal-1", "dup")
	publish(t, js, "bal-1", "dup") // 同样的 raw ⇒ 同样的 event_id

	if !waitFor(t, 10*time.Second, func() bool { return f.count() >= 1 }) {
		t.Fatal("读数没有投递")
	}
	time.Sleep(700 * time.Millisecond)
	if got := f.count(); got != 1 {
		t.Errorf("重复 event_id 只应入库一条，实际 %d 条", got)
	}
}

// LIMS 不可用时不该丢数据，恢复后要补上。
func TestSurvivesLIMSOutage(t *testing.T) {
	js := startHub(t)
	f := newFakeLIMS(t)
	f.setListening("bal-1", true)
	runBridge(t, js, f, time.Hour)

	publish(t, js, "bal-1", "before-outage")
	if !waitFor(t, 10*time.Second, func() bool { return contains(f.raw(), "before-outage") }) {
		t.Fatal("首条读数没有投递")
	}

	f.srv.CloseClientConnections()
	f.srv.Config.SetKeepAlivesEnabled(false)
	publish(t, js, "bal-1", "during-outage")

	if !waitFor(t, 15*time.Second, func() bool { return contains(f.raw(), "during-outage") }) {
		t.Errorf("LIMS 抖动期间的读数没有补投，实际收到 %v", f.raw())
	}
}

// 没有会话时不该反复敲 LIMS 的 ingest 接口 —— 否则日志会被刷满。
func TestDoesNotHammerIngestWithoutSession(t *testing.T) {
	js := startHub(t)
	f := newFakeLIMS(t)
	f.setListening("bal-1", false)
	for i := range 10 {
		publish(t, js, "bal-1", fmt.Sprintf("idle-%d", i))
	}

	runBridge(t, js, f, time.Hour)
	time.Sleep(2 * time.Second)

	// 轮询间隔 200ms，两秒里若靠重试硬怼会有几十上百次
	if hits := f.hits(); hits > 3 {
		t.Errorf("没有会话时不该反复调 ingest，2 秒内调了 %d 次", hits)
	}
}

func contains(list []string, want string) bool {
	for _, s := range list {
		if s == want {
			return true
		}
	}
	return false
}
