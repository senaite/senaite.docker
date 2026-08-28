package httpapi_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"net/http/cookiejar"
	"net/http/httptest"
	"net/url"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/maitux/labgate/internal/acquire"
	"github.com/maitux/labgate/internal/bus"
	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/httpapi"
	"github.com/maitux/labgate/internal/ingest"
	"github.com/maitux/labgate/internal/limspoll"
	"github.com/maitux/labgate/internal/logx"
	"github.com/maitux/labgate/internal/state"
)

// newTestServer 起一个完整的采集端（内嵌 NATS，不连云端）。
func newTestServer(t *testing.T) (*httptest.Server, *config.Store) {
	t.Helper()
	dir := t.TempDir()
	store, err := config.Load(filepath.Join(dir, "config.json"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.Update(map[string]any{
		"cache": map[string]any{"dir": dir},
		"agent": map[string]any{"instrument_code": "bal-1"},
	}); err != nil {
		t.Fatal(err)
	}

	log := logx.New(200, slog.New(slog.DiscardHandler))
	st := state.New(100)
	ctx, cancel := context.WithCancel(context.Background())

	b, err := bus.Start(ctx, store.Get(), log)
	if err != nil {
		cancel()
		t.Fatal(err)
	}
	if _, err := b.EnsureLocalStream(ctx); err != nil {
		cancel()
		b.Close()
		t.Fatal(err)
	}

	ing := ingest.New(b.LocalJS(), store.Get, st, log)
	mgr := acquire.NewManager(ctx, store.Get,
		func(ctx context.Context, code, raw, value, unit string, push bool) {
			ing.Submit(ctx, code, raw, value, unit, push) //nolint:errcheck // 测试里不关心
		}, log)

	srv, err := httpapi.New(httpapi.Deps{
		Config:  store,
		State:   st,
		Log:     log,
		Acquire: mgr,
		Ingest:  ing,
		Bus:     b,
		Poller:  limspoll.New(store.Get, mgr, st, log),
		Version: "test",
	})
	if err != nil {
		cancel()
		b.Close()
		t.Fatal(err)
	}

	ts := httptest.NewServer(srv.Handler())
	t.Cleanup(func() {
		ts.Close()
		cancel()
		mgr.Close()
		b.Close()
	})
	return ts, store
}

func getJSON(t *testing.T, ts *httptest.Server, path string) map[string]any {
	t.Helper()
	resp, err := http.Get(ts.URL + path)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("GET %s 响应不是合法 JSON: %v", path, err)
	}
	return out
}

func postJSON(t *testing.T, ts *httptest.Server, path string, body any) (int, map[string]any) {
	t.Helper()
	data, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	resp, err := http.Post(ts.URL+path, "application/json", bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatalf("POST %s 响应不是合法 JSON: %v", path, err)
	}
	return resp.StatusCode, out
}

// /api/state 必须保留旧采集端的字段，云 LIMS 侧的调用才不用改。
func TestStateKeepsLegacyShape(t *testing.T) {
	ts, _ := newTestServer(t)
	out := getJSON(t, ts, "/api/state")

	for _, key := range []string{
		"mode", "connected", "connecting", "last_message",
		"current_host", "current_port", "stats", "config",
		"instruments", "cloud_last_pull", "cloud_last_error",
	} {
		if _, ok := out[key]; !ok {
			t.Errorf("/api/state 缺少旧字段 %q", key)
		}
	}
	stats, ok := out["stats"].(map[string]any)
	if !ok {
		t.Fatal("stats 不是对象")
	}
	for _, key := range []string{
		"total_received", "total_parsed", "push_ok",
		"push_fail", "push_skipped", "cache_pending",
	} {
		if _, ok := stats[key]; !ok {
			t.Errorf("stats 缺少旧字段 %q", key)
		}
	}
}

// /api/state 里的凭据要脱敏（这个接口会被 LIMS 反复轮询）。
func TestStateRedactsSecrets(t *testing.T) {
	ts, store := newTestServer(t)
	if _, err := store.Update(map[string]any{
		"cloud": map[string]any{"token": "super-secret"},
		"nats": map[string]any{"leaf": map[string]any{
			"password": "pw",
			// 密码常常直接写在 LeafNode 地址里
			"url": "nats-leaf://labgate:pw@hub.example.com:7422",
		}},
	}); err != nil {
		t.Fatal(err)
	}

	out := getJSON(t, ts, "/api/state")
	cfg := out["config"].(map[string]any)
	if got := cfg["cloud"].(map[string]any)["token"]; got != "***" {
		t.Errorf("/api/state 里的 token 没有脱敏: %v", got)
	}
	leaf := cfg["nats"].(map[string]any)["leaf"].(map[string]any)
	if got := leaf["password"]; got != "***" {
		t.Errorf("/api/state 里的 leaf 密码没有脱敏: %v", got)
	}
	if got, _ := leaf["url"].(string); strings.Contains(got, "pw@") {
		t.Errorf("LeafNode 地址里的密码没有脱敏: %v", got)
	}
	// 状态页展示的也是同一份地址，同样不能带密码
	if got, _ := out["cloud"].(map[string]any)["leaf_url"].(string); strings.Contains(got, "pw@") {
		t.Errorf("cloud.leaf_url 里的密码没有脱敏: %v", got)
	}

	// 配置页要拿原值，/api/config 不脱敏
	cfgOut := getJSON(t, ts, "/api/config")
	if got := cfgOut["cloud"].(map[string]any)["token"]; got != "super-secret" {
		t.Errorf("/api/config 应返回原始 token，得到 %v", got)
	}
}

// 改动 NATS 段要提示重启，改其他段不用。
func TestConfigUpdateRestartHint(t *testing.T) {
	ts, _ := newTestServer(t)

	_, out := postJSON(t, ts, "/api/config", map[string]any{
		"cloud": map[string]any{"lims_url": "http://lims:8080"},
	})
	if out["restart_required"] != false {
		t.Error("只改 cloud 段不该要求重启")
	}

	_, out = postJSON(t, ts, "/api/config", map[string]any{
		"nats": map[string]any{"leaf": map[string]any{"url": "nats-leaf://hub:7422"}},
	})
	if out["restart_required"] != true {
		t.Error("改 nats.leaf 应提示重启")
	}
	// 局部更新不能把先前保存的值冲掉
	cfg := getJSON(t, ts, "/api/config")
	if got := cfg["cloud"].(map[string]any)["lims_url"]; got != "http://lims:8080" {
		t.Errorf("先前保存的 lims_url 被冲掉了: %v", got)
	}
}

// /api/start_sync 连不上仪器时返回 200 + success:false（旧行为，LIMS 靠 message 提示操作员）。
func TestStartSyncReportsUnreachableInstrument(t *testing.T) {
	ts, _ := newTestServer(t)

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := ln.Addr().(*net.TCPAddr).Port
	ln.Close() // 释放端口，制造"连不上"

	status, out := postJSON(t, ts, "/api/start_sync", map[string]any{
		"code": "bal-1", "host": "127.0.0.1", "port": port,
	})
	if status != http.StatusOK {
		t.Errorf("状态码应为 200（旧行为），得到 %d", status)
	}
	if out["success"] != false {
		t.Error("连不上仪器时 success 应为 false")
	}
	if msg, _ := out["message"].(string); msg == "" {
		t.Error("失败时应带 message 供 LIMS 展示")
	}
}

// /api/start_sync 能连通时应真正开始采集。
func TestStartSyncStartsAcquisition(t *testing.T) {
	ts, _ := newTestServer(t)

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			go func() {
				defer conn.Close()
				conn.Write([]byte("ST,GS,0.9678,mg\n"))
				time.Sleep(2 * time.Second)
			}()
		}
	}()
	port := ln.Addr().(*net.TCPAddr).Port

	_, out := postJSON(t, ts, "/api/start_sync", map[string]any{
		"code": "bal-1", "host": "127.0.0.1", "port": port,
	})
	if out["success"] != true {
		t.Fatalf("应连接成功: %v", out)
	}

	// 采到的读数应出现在 /api/readings
	deadline := time.Now().Add(5 * time.Second)
	var readings []any
	for time.Now().Before(deadline) {
		r := getJSON(t, ts, "/api/readings?limit=10")
		readings, _ = r["readings"].([]any)
		if len(readings) > 0 {
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	if len(readings) == 0 {
		t.Fatal("开始采集后 /api/readings 仍为空")
	}
	row := readings[0].(map[string]any)
	if row["raw"] != "ST,GS,0.9678,mg" || row["value"] != "0.9678" {
		t.Errorf("读数内容有误: %v", row)
	}

	// 按 code 查询单台仪器状态（LIMS 会这样调）
	one := getJSON(t, ts, "/api/state?code=bal-1")
	if one["connected"] != true {
		t.Errorf("/api/state?code= 应显示已连接: %v", one)
	}

	postJSON(t, ts, "/api/stop", map[string]any{"code": "bal-1"})
}

// 端口写成字符串也要能接受（旧调用方两种都发过）。
func TestStartAcceptsStringPort(t *testing.T) {
	ts, _ := newTestServer(t)
	status, out := postJSON(t, ts, "/api/start", map[string]any{
		"code": "bal-1", "host": "127.0.0.1", "port": "9999",
	})
	if status != http.StatusOK || out["success"] != true {
		t.Errorf("字符串端口应被接受，得到 %d %v", status, out)
	}
	postJSON(t, ts, "/api/stop", map[string]any{})
}

// 缺 IP / 端口非法时返回 400。
func TestStartValidatesInput(t *testing.T) {
	ts, _ := newTestServer(t)
	if status, _ := postJSON(t, ts, "/api/start", map[string]any{"port": 9000}); status != 400 {
		t.Errorf("缺 host 应返回 400，得到 %d", status)
	}
	if status, _ := postJSON(t, ts, "/api/start",
		map[string]any{"host": "1.2.3.4", "port": "abc"}); status != 400 {
		t.Errorf("端口非法应返回 400，得到 %d", status)
	}
}

// /api/http_test 注入的读数要真正落进 JetStream。
func TestInjectReadingReachesStream(t *testing.T) {
	ts, _ := newTestServer(t)

	_, out := postJSON(t, ts, "/api/http_test", map[string]any{
		"raw_text": "ST,GS,1.2345,mg",
	})
	if out["success"] != true {
		t.Fatalf("注入失败: %v", out)
	}
	eventID, _ := out["event_id"].(string)
	if eventID == "" {
		t.Error("应返回 event_id（云端幂等去重靠它）")
	}
	parsed := out["parsed"].(map[string]any)
	if parsed["value"] != "1.2345" || parsed["unit"] != "mg" {
		t.Errorf("解析结果有误: %v", parsed)
	}

	stats := getJSON(t, ts, "/api/stats")
	stream, ok := stats["stream"].(map[string]any)
	if !ok {
		t.Fatal("/api/stats 缺少 stream 段")
	}
	if msgs, _ := stream["messages"].(float64); msgs < 1 {
		t.Errorf("注入的读数没有进入 JetStream，messages=%v", stream["messages"])
	}
	// cache 段保持旧字段名
	if _, ok := stats["cache"].(map[string]any)["pending"]; !ok {
		t.Error("/api/stats 缺少旧的 cache.pending 字段")
	}
}

func TestTokenRegenerate(t *testing.T) {
	ts, store := newTestServer(t)
	_, out := postJSON(t, ts, "/api/token/regenerate", map[string]any{})
	token, _ := out["token"].(string)
	if len(token) < 20 {
		t.Fatalf("生成的 Token 太短: %q", token)
	}
	if store.Get().Cloud.Token != token {
		t.Error("新 Token 没有写入配置")
	}
}

func TestTCPTest(t *testing.T) {
	ts, _ := newTestServer(t)

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			conn.Close()
		}
	}()
	port := ln.Addr().(*net.TCPAddr).Port

	_, out := postJSON(t, ts, "/api/tcp_test",
		map[string]any{"host": "127.0.0.1", "port": port})
	if out["success"] != true {
		t.Errorf("应连通: %v", out)
	}
}

// 五个页面与静态资源都要能打开（离线可用，不依赖 CDN）。
func TestPagesRender(t *testing.T) {
	ts, _ := newTestServer(t)
	for _, path := range []string{
		"/", "/status", "/debug", "/config_page", "/logs",
		"/static/style.css", "/static/app.js", "/healthz",
	} {
		resp, err := http.Get(ts.URL + path)
		if err != nil {
			t.Fatalf("GET %s: %v", path, err)
		}
		body := make([]byte, 64)
		n, _ := resp.Body.Read(body)
		resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			t.Errorf("GET %s 返回 %d", path, resp.StatusCode)
		}
		if n == 0 {
			t.Errorf("GET %s 返回空内容", path)
		}
	}
}

// 空请求体不应导致 500（旧采集端把空 body 当空对象）。
func TestEmptyBodyTolerated(t *testing.T) {
	ts, _ := newTestServer(t)
	resp, err := http.Post(ts.URL+"/api/stop", "application/json", nil)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	// S2 防御：空 body 的 /api/stop 不再静默停全部，返回 400 提示
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("空 body 的 /api/stop 应返回 400，得到 %d", resp.StatusCode)
	}
}

// 显式 all=true 的 /api/stop 仍然可以停止全部仪器。
func TestStopAllExplicit(t *testing.T) {
	ts, _ := newTestServer(t)
	status, out := postJSON(t, ts, "/api/stop", map[string]any{"all": true})
	if status != http.StatusOK {
		t.Fatalf("all=true 的 /api/stop 应返回 200，得到 %d", status)
	}
	if !out["success"].(bool) {
		t.Errorf("all=true 的 /api/stop 应 success:true，得到 %v", out)
	}
}

// 未配置 LIMS 时 /api/pull_now 要给出可读的失败原因，而不是 500。
func TestPullNowWithoutLIMS(t *testing.T) {
	ts, _ := newTestServer(t)
	status, out := postJSON(t, ts, "/api/pull_now", map[string]any{})
	if status != http.StatusOK {
		t.Errorf("应返回 200，得到 %d", status)
	}
	if out["success"] != false {
		t.Errorf("未配置 LIMS 时 success 应为 false: %v", out)
	}
	if msg, _ := out["message"].(string); msg == "" {
		t.Error("应说明失败原因")
	}
}

func TestLogsEndpoint(t *testing.T) {
	ts, _ := newTestServer(t)
	postJSON(t, ts, "/api/config", map[string]any{"agent": map[string]any{"mode": "manual"}})

	out := getJSON(t, ts, "/api/logs")
	logs, ok := out["logs"].([]any)
	if !ok {
		t.Fatal("/api/logs 缺少 logs 数组")
	}
	if len(logs) == 0 {
		t.Fatal("应至少有一条日志")
	}
	entry := logs[0].(map[string]any)
	for _, key := range []string{"time", "level", "message"} {
		if _, ok := entry[key]; !ok {
			t.Errorf("日志条目缺少字段 %q: %v", key, entry)
		}
	}
	if fmt.Sprint(entry["message"]) == "" {
		t.Error("日志内容为空")
	}
}

// 配了 agent.admin_password 后，网页与界面接口都要先登录；
// 云 LIMS 联动的三个接口不受影响（LIMS 侧不会登录）。
func TestLoginProtectsUI(t *testing.T) {
	ts, store := newTestServer(t)
	if _, err := store.Update(map[string]any{
		"agent": map[string]any{"admin_user": "admin", "admin_password": "test-pw-9f3a"},
	}); err != nil {
		t.Fatal(err)
	}

	// 不跟随跳转，好确认拿到的是 302 而不是被重定向后的 200
	noRedirect := &http.Client{CheckRedirect: func(*http.Request, []*http.Request) error {
		return http.ErrUseLastResponse
	}}
	get := func(c *http.Client, path string) *http.Response {
		t.Helper()
		resp, err := c.Get(ts.URL + path)
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { resp.Body.Close() })
		return resp
	}

	if resp := get(noRedirect, "/"); resp.StatusCode != http.StatusFound {
		t.Errorf("未登录访问首页应跳登录页，得到 %d", resp.StatusCode)
	} else if loc := resp.Header.Get("Location"); !strings.HasPrefix(loc, "/login") {
		t.Errorf("跳转目标应是 /login，得到 %q", loc)
	}
	if resp := get(noRedirect, "/api/readings"); resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("未登录调界面接口应 401，得到 %d", resp.StatusCode)
	}
	if resp := get(noRedirect, "/login"); resp.StatusCode != http.StatusOK {
		t.Errorf("登录页本身应可访问，得到 %d", resp.StatusCode)
	}
	// LIMS 联动接口与健康检查不参与登录
	for _, path := range []string{"/api/state", "/healthz"} {
		if resp := get(noRedirect, path); resp.StatusCode != http.StatusOK {
			t.Errorf("%s 不该要求登录，得到 %d", path, resp.StatusCode)
		}
	}

	login := func(c *http.Client, user, pass string) *http.Response {
		t.Helper()
		resp, err := c.PostForm(ts.URL+"/login", url.Values{
			"user": {user}, "password": {pass},
		})
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { resp.Body.Close() })
		return resp
	}

	if resp := login(noRedirect, "admin", "wrong"); resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("密码错应 401，得到 %d", resp.StatusCode)
	}

	jar, err := cookiejar.New(nil)
	if err != nil {
		t.Fatal(err)
	}
	client := &http.Client{Jar: jar}
	if resp := login(client, "admin", "test-pw-9f3a"); resp.StatusCode != http.StatusOK {
		t.Fatalf("登录后应跳回首页并渲染成功，得到 %d", resp.StatusCode)
	}
	for _, path := range []string{"/", "/config_page", "/api/readings", "/api/config"} {
		if resp := get(client, path); resp.StatusCode != http.StatusOK {
			t.Errorf("登录后访问 %s 应成功，得到 %d", path, resp.StatusCode)
		}
	}

	if resp := get(client, "/logout"); resp.StatusCode != http.StatusOK {
		t.Fatalf("退出后应落到登录页，得到 %d", resp.StatusCode)
	}
	if resp := get(client, "/api/readings"); resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("退出后接口应回到 401，得到 %d", resp.StatusCode)
	}
}

// 管理密码会写进 config.json，/api/state 被 LIMS 反复轮询，必须脱敏。
func TestStateRedactsAdminPassword(t *testing.T) {
	ts, store := newTestServer(t)
	if _, err := store.Update(map[string]any{
		"agent": map[string]any{"admin_password": "test-pw-9f3a"},
	}); err != nil {
		t.Fatal(err)
	}
	out := getJSON(t, ts, "/api/state")
	agent := out["config"].(map[string]any)["agent"].(map[string]any)
	if got := agent["admin_password"]; got != "***" {
		t.Errorf("/api/state 里的管理密码没有脱敏: %v", got)
	}
}
