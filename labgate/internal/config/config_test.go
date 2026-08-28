package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// 旧 Python 采集端的 config.json 必须能被直接读取，缺失的新键补默认值。
func TestLoadLegacyConfig(t *testing.T) {
	legacy := `{
  "agent": {"host": "0.0.0.0", "port": 8090, "mode": "auto",
            "instrument_code": "instrument-3", "push_enabled": true},
  "cloud": {"lims_url": "http://192.168.1.18:8081/lims",
            "token": "maitux-phase1-token",
            "config_poll_seconds": 10, "push_timeout_seconds": 10},
  "instrument": {"host": "192.168.1.5", "port": 55097,
                 "connect_timeout_seconds": 3, "reconnect_delay_seconds": 3,
                 "line_terminator": "\n"},
  "cache": {"dir": "data", "db_file": "agent_cache.db",
            "max_retries": 5, "retry_delay_seconds": 2},
  "instruments": [{"code": "instrument-3", "host": "192.168.1.5",
                   "port": 55097, "enabled": true}]
}`
	dir := t.TempDir()
	path := filepath.Join(dir, "config.json")
	if err := os.WriteFile(path, []byte(legacy), 0o644); err != nil {
		t.Fatal(err)
	}

	store, err := Load(path)
	if err != nil {
		t.Fatalf("加载旧配置失败: %v", err)
	}
	cfg := store.Get()

	if cfg.Agent.Port != 8090 || cfg.Agent.InstrumentCode != "instrument-3" {
		t.Errorf("agent 段读取有误: %+v", cfg.Agent)
	}
	if cfg.Cloud.LIMSURL != "http://192.168.1.18:8081/lims" {
		t.Errorf("cloud.lims_url 读取有误: %q", cfg.Cloud.LIMSURL)
	}
	if cfg.Instrument.Port != 55097 {
		t.Errorf("instrument.port 读取有误: %d", cfg.Instrument.Port)
	}
	// 旧配置里没有的新键必须补上默认值
	if cfg.NATS.Stream != "READINGS" || cfg.NATS.Domain != "edge" {
		t.Errorf("nats 默认值没有补齐: %+v", cfg.NATS)
	}
	if cfg.Instrument.IdleFlushMilliseconds != 500 {
		t.Errorf("idle_flush_milliseconds 默认值没有补齐: %d",
			cfg.Instrument.IdleFlushMilliseconds)
	}
	// 旧配置没有 lims_push_enabled，默认必须是关闭
	if cfg.Cloud.LIMSPushEnabled {
		t.Error("lims_push_enabled 默认应为 false")
	}

	insts := cfg.EnabledInstruments()
	if len(insts) != 1 || insts[0].Code != "instrument-3" || insts[0].Port != 55097 {
		t.Errorf("仪器清单解析有误: %+v", insts)
	}
}

// 没有 instruments 列表时回退到旧的单仪器字段。
func TestEnabledInstrumentsFallback(t *testing.T) {
	cfg := Defaults()
	cfg.Agent.InstrumentCode = "balance-1"
	cfg.Instrument.Host = "10.0.0.5"
	cfg.Instrument.Port = 9000

	insts := cfg.EnabledInstruments()
	if len(insts) != 1 {
		t.Fatalf("期望回退出 1 台仪器，得到 %d", len(insts))
	}
	if insts[0].Code != "balance-1" || insts[0].Host != "10.0.0.5" {
		t.Errorf("回退结果有误: %+v", insts[0])
	}

	// 缺 host 时不应该产出仪器
	cfg.Instrument.Host = ""
	if got := cfg.EnabledInstruments(); len(got) != 0 {
		t.Errorf("缺少 host 时不应产出仪器，得到 %+v", got)
	}
}

// 界面提交的局部配置必须深合并，不能把同段其他键清空。
func TestUpdateDeepMerge(t *testing.T) {
	dir := t.TempDir()
	store, err := Load(filepath.Join(dir, "config.json"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.Update(map[string]any{
		"cloud": map[string]any{"lims_url": "http://lims:8080"},
	}); err != nil {
		t.Fatal(err)
	}
	cfg, err := store.Update(map[string]any{
		"cloud": map[string]any{"token": "abc"},
		"nats":  map[string]any{"leaf": map[string]any{"url": "nats-leaf://hub:7422"}},
	})
	if err != nil {
		t.Fatal(err)
	}

	if cfg.Cloud.LIMSURL != "http://lims:8080" {
		t.Errorf("第二次更新把 lims_url 冲掉了: %q", cfg.Cloud.LIMSURL)
	}
	if cfg.Cloud.Token != "abc" {
		t.Errorf("token 没有写入: %q", cfg.Cloud.Token)
	}
	if cfg.NATS.Leaf.URL != "nats-leaf://hub:7422" {
		t.Errorf("嵌套的 leaf.url 没有写入: %q", cfg.NATS.Leaf.URL)
	}
	// 嵌套更新不能清掉同层的其他默认值
	if cfg.NATS.Leaf.HubDomain != "hub" || cfg.NATS.Leaf.HubStream != "LAB_READINGS" {
		t.Errorf("leaf 段其他默认值被清空: %+v", cfg.NATS.Leaf)
	}
	if cfg.NATS.Stream != "READINGS" {
		t.Errorf("nats 段其他默认值被清空: %q", cfg.NATS.Stream)
	}

	// 落盘内容必须能被重新读回
	reloaded, err := Load(store.Path())
	if err != nil {
		t.Fatal(err)
	}
	if reloaded.Get().Cloud.Token != "abc" {
		t.Error("更新后的配置没有正确落盘")
	}
}

// instruments 这类列表在更新时应整体替换，而不是逐项合并。
func TestUpdateReplacesInstrumentList(t *testing.T) {
	dir := t.TempDir()
	store, _ := Load(filepath.Join(dir, "config.json"))
	if _, err := store.Update(map[string]any{
		"instruments": []any{
			map[string]any{"code": "a", "host": "1.1.1.1", "port": 9000, "enabled": true},
			map[string]any{"code": "b", "host": "2.2.2.2", "port": 9000, "enabled": true},
		},
	}); err != nil {
		t.Fatal(err)
	}
	cfg, err := store.Update(map[string]any{
		"instruments": []any{
			map[string]any{"code": "c", "host": "3.3.3.3", "port": 9000, "enabled": true},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(cfg.Instruments) != 1 || cfg.Instruments[0].Code != "c" {
		t.Errorf("仪器清单应被整体替换，得到 %+v", cfg.Instruments)
	}
}

// 带 UTF-8 BOM 的配置文件（Windows 编辑器常见）必须能读。
func TestLoadWithBOM(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config.json")
	body := append([]byte{0xEF, 0xBB, 0xBF}, []byte(`{"agent":{"port":9999}}`)...)
	if err := os.WriteFile(path, body, 0o644); err != nil {
		t.Fatal(err)
	}
	store, err := Load(path)
	if err != nil {
		t.Fatalf("带 BOM 的配置读取失败: %v", err)
	}
	if store.Get().Agent.Port != 9999 {
		t.Errorf("端口读取有误: %d", store.Get().Agent.Port)
	}
}

// 环境变量覆盖（Docker 首次启动用）。
func TestEnvOverride(t *testing.T) {
	t.Setenv("LABGATE_PORT", "8099")
	t.Setenv("LABGATE_SITE_ID", "lab-x")
	t.Setenv("LABGATE_LEAF_URL", "nats-leaf://hub:7422")

	store, err := Load(filepath.Join(t.TempDir(), "config.json"))
	if err != nil {
		t.Fatal(err)
	}
	cfg := store.Get()
	if cfg.Agent.Port != 8099 || cfg.Agent.SiteID != "lab-x" {
		t.Errorf("环境变量没有生效: %+v", cfg.Agent)
	}
	// 填了 leaf url 就应自动启用 LeafNode
	if !cfg.NATS.Leaf.Enabled {
		t.Error("设置 LABGATE_LEAF_URL 后应自动启用 LeafNode")
	}
}

// 主题里的 code / site_id 含 . 或 * 时必须被转义，否则会破坏 NATS 主题结构。
func TestSubjectSanitize(t *testing.T) {
	cfg := Defaults()
	cfg.Agent.SiteID = "lab.shanghai"
	if got := cfg.LocalSubject("bal.01"); got != "edge.readings.bal_01" {
		t.Errorf("本地主题有误: %q", got)
	}
	if got := cfg.HubSubject("bal*01"); got != "lab.lab_shanghai.readings.bal_01" {
		t.Errorf("云端主题有误: %q", got)
	}
	if got := cfg.LocalSubject(""); got != "edge.readings.unknown" {
		t.Errorf("空 code 应回落到 unknown，得到 %q", got)
	}
}

// 首次运行（配置文件不存在）应生成一份完整的默认配置。
func TestLoadCreatesDefaultFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "sub", "config.json")
	store, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(store.Path())
	if err != nil {
		t.Fatalf("默认配置没有落盘: %v", err)
	}
	var out Config
	if err := json.Unmarshal(data, &out); err != nil {
		t.Fatalf("落盘的配置不是合法 JSON: %v", err)
	}
	if out.Agent.Port != 8090 {
		t.Errorf("默认端口有误: %d", out.Agent.Port)
	}
}

// LeafNode 地址里的密码不能出现在日志或状态接口里。
func TestLeafSafeURL(t *testing.T) {
	cases := []struct{ in, want string }{
		{"nats-leaf://user:secret@hub:7422", "nats-leaf://user@hub:7422"},
		{"nats-leaf://user@hub:7422", "nats-leaf://user@hub:7422"},
		{"nats-leaf://hub:7422", "nats-leaf://hub:7422"},
		{"", ""},
		{"::not a url::", "::not a url::"},
	}
	for _, tc := range cases {
		if got := (Leaf{URL: tc.in}).SafeURL(); got != tc.want {
			t.Errorf("SafeURL(%q) = %q, 期望 %q", tc.in, got, tc.want)
		}
	}
}

// 仪器条目不写 enabled / push 时应视为开启（旧采集端的行为）。
// 写成普通 bool 会让这类条目静悄悄地不采集、不上传。
func TestInstrumentDefaultsToEnabledAndPush(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config.json")
	// 只写必填项，enabled 与 push 都省略
	body := `{"instruments":[{"code":"bal-1","host":"10.0.0.5","port":9000}]}`
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	store, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}

	insts := store.Get().EnabledInstruments()
	if len(insts) != 1 {
		t.Fatalf("省略 enabled 的仪器应被采集，实际得到 %d 台", len(insts))
	}
	if !insts[0].ShouldPush() {
		t.Error("省略 push 的仪器应上传")
	}

	// 显式写 false 时必须生效
	no := false
	cfg := Defaults()
	cfg.Instruments = []InstrumentEntry{
		{Code: "a", Host: "1.1.1.1", Port: 9000, Enabled: &no},
		{Code: "b", Host: "2.2.2.2", Port: 9000, Push: &no},
	}
	insts = cfg.EnabledInstruments()
	if len(insts) != 1 || insts[0].Code != "b" {
		t.Fatalf("enabled:false 的仪器应被跳过，得到 %+v", insts)
	}
	if insts[0].ShouldPush() {
		t.Error("push:false 应生效")
	}
}
