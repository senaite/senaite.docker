// Package config 负责配置的加载、合并、热更新与落盘。
//
// 配置文件沿用旧 Python 采集端的 config.json 结构（agent / cloud /
// instrument / instruments / cache），新增 nats 段用于 NATS LeafNode 与
// JetStream。旧配置文件可直接使用，缺失的键由默认值补齐。
package config

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Agent 是采集端自身的运行参数。
type Agent struct {
	Host           string `json:"host"`
	Port           int    `json:"port"`
	Mode           string `json:"mode"`            // auto=跟随云 | manual=界面手动
	SiteID         string `json:"site_id"`         // 站点标识（多实验室时区分）
	InstrumentCode string `json:"instrument_code"` // 兼容旧单仪器配置
	PushEnabled    bool   `json:"push_enabled"`
	// APIToken 是本机管理接口（/api/config、/api/start、/api/stop 等）的
	// 可选鉴权令牌。为空时不鉴权（兼容旧部署）；非空时管理接口要求
	// Authorization: Bearer <token>。云 LIMS 调用的 /api/state、
	// /api/start_sync 等联动接口不受此限制（LIMS 无此令牌）。
	APIToken string `json:"api_token"`
}

// InstrumentEntry 是仪器清单中的一台仪器（自动模式下由 LIMS 下发时可为空）。
//
// Enabled 与 Push 用指针，是为了区分"写了 false"和"没写"：
// 旧采集端里这两项缺省都当 true，写成普通 bool 会让
// {"code":"a","host":"1.2.3.4","port":9000} 这种条目静悄悄地不采集、不上传。
type InstrumentEntry struct {
	Code    string `json:"code"`
	Host    string `json:"host"`
	Port    int    `json:"port"`
	Enabled *bool  `json:"enabled,omitempty"`
	Push    *bool  `json:"push,omitempty"`
}

// IsEnabled 返回是否采集这台仪器（缺省为是）。
func (i InstrumentEntry) IsEnabled() bool { return i.Enabled == nil || *i.Enabled }

// ShouldPush 返回这台仪器的读数是否要落盘上传（缺省为是）。
// agent.push_enabled 是总开关，两者都为真才会上传。
func (i InstrumentEntry) ShouldPush() bool { return i.Push == nil || *i.Push }

// Cloud 是云 LIMS（SENAITE）HTTP 对接参数。
//
// 第一阶段可完全不填：留空即关闭 HTTP 直连，读数只走 NATS LeafNode 上云。
type Cloud struct {
	LIMSURL            string `json:"lims_url"`
	Token              string `json:"token"`
	ConfigPollSeconds  int    `json:"config_poll_seconds"`
	PushTimeoutSeconds int    `json:"push_timeout_seconds"`
	// LIMSPushEnabled 控制是否把读数用 HTTP 直推 SENAITE ingest 接口。
	// 默认 false：读数经 NATS 上云；需要与 SENAITE 直连时打开。
	LIMSPushEnabled bool `json:"lims_push_enabled"`
	// PollEnabled 控制是否轮询 LIMS 拉取仪器清单（自动模式）。
	PollEnabled bool `json:"poll_enabled"`
}

// Instrument 是所有仪器共用的 TCP 连接参数。
type Instrument struct {
	Host                  string `json:"host"`
	Port                  int    `json:"port"`
	ConnectTimeoutSeconds int    `json:"connect_timeout_seconds"`
	ReconnectDelaySeconds int    `json:"reconnect_delay_seconds"`
	LineTerminator        string `json:"line_terminator"`
	IdleFlushMilliseconds int    `json:"idle_flush_milliseconds"`
	MaxLineBytes          int    `json:"max_line_bytes"`
}

// Cache 保留旧配置键位，语义映射到 JetStream 本地留存与重投策略。
type Cache struct {
	Dir               string `json:"dir"`
	MaxRetries        int    `json:"max_retries"`
	RetryDelaySeconds int    `json:"retry_delay_seconds"`
}

// Leaf 是 NATS LeafNode（连接云端 NATS 集群）的参数。
type Leaf struct {
	Enabled     bool   `json:"enabled"`
	URL         string `json:"url"` // nats-leaf://host:7422
	User        string `json:"user"`
	Password    string `json:"password"`
	Credentials string `json:"credentials"` // .creds 文件路径（优先于账号密码）
	// HubDomain 是云端 JetStream 域名，用于把管理请求路由到云端。
	HubDomain string `json:"hub_domain"`
	// HubStream / HubSubjectPrefix 是云端读数流及其主题前缀。
	HubStream        string `json:"hub_stream"`
	HubSubjectPrefix string `json:"hub_subject_prefix"`
	// EnsureHubStream：启动时若云端没有该流则自动创建（自建云端时方便，
	// 云端由他人管理时应关闭）。
	EnsureHubStream   bool `json:"ensure_hub_stream"`
	AckTimeoutSeconds int  `json:"ack_timeout_seconds"`
	// RetryDelaySeconds 是云端不可用时的重投递退避秒数。
	RetryDelaySeconds int  `json:"retry_delay_seconds"`
	TLSInsecure       bool `json:"tls_insecure"`
}

// SafeURL 返回抹掉密码的 LeafNode 地址。
//
// 地址常写成 nats-leaf://user:pass@host:7422，而日志和 /api/state 都是
// 无鉴权就能看到的，所以凡是要展示这个地址的地方都应该走这里。
func (l Leaf) SafeURL() string {
	if l.URL == "" {
		return ""
	}
	u, err := url.Parse(l.URL)
	if err != nil || u.User == nil {
		return l.URL
	}
	if _, hasPassword := u.User.Password(); hasPassword {
		// 只留用户名：填 "***" 当密码会被百分号编码成 %2A%2A%2A，很难看
		u.User = url.User(u.User.Username())
	}
	return u.String()
}

// NATS 是内嵌 NATS 服务器（含 JetStream 持久化）的参数。
type NATS struct {
	ServerName string `json:"server_name"`
	// Listen 为空表示不监听 TCP 端口，采集端以进程内方式连接（Windows 下
	// 不会触发防火墙弹窗）；填 "127.0.0.1:4222" 可用 nats CLI 观察。
	Listen        string `json:"listen"`
	MonitorListen string `json:"monitor_listen"` // 如 "127.0.0.1:8222"，空=关闭
	StoreDir      string `json:"store_dir"`      // 空=<data_dir>/jetstream
	Domain        string `json:"domain"`         // 边缘侧 JetStream 域
	Stream        string `json:"stream"`         // 边缘侧读数流名
	SubjectPrefix string `json:"subject_prefix"` // 边缘侧主题前缀
	MaxAgeHours   int    `json:"max_age_hours"`
	MaxBytesMB    int    `json:"max_bytes_mb"`
	MaxMsgs       int64  `json:"max_msgs"`
	Leaf          Leaf   `json:"leaf"`
}

// Config 是完整配置。
type Config struct {
	Agent       Agent             `json:"agent"`
	Instruments []InstrumentEntry `json:"instruments"`
	Cloud       Cloud             `json:"cloud"`
	Instrument  Instrument        `json:"instrument"`
	Cache       Cache             `json:"cache"`
	NATS        NATS              `json:"nats"`
}

// Defaults 返回一份可直接运行的默认配置。
func Defaults() Config {
	return Config{
		Agent: Agent{
			Host:        "0.0.0.0",
			Port:        8090,
			Mode:        "auto",
			SiteID:      "site-1",
			PushEnabled: true,
		},
		Instruments: []InstrumentEntry{},
		Cloud: Cloud{
			ConfigPollSeconds:  10,
			PushTimeoutSeconds: 10,
			LIMSPushEnabled:    false,
			PollEnabled:        false,
		},
		Instrument: Instrument{
			Port:                  9000,
			ConnectTimeoutSeconds: 3,
			ReconnectDelaySeconds: 3,
			LineTerminator:        "\n",
			IdleFlushMilliseconds: 500,
			MaxLineBytes:          64 * 1024,
		},
		Cache: Cache{
			Dir:               "data",
			MaxRetries:        5,
			RetryDelaySeconds: 5,
		},
		NATS: NATS{
			ServerName:    "labgate",
			Listen:        "",
			Domain:        "edge",
			Stream:        "READINGS",
			SubjectPrefix: "edge",
			MaxAgeHours:   24 * 14,
			MaxBytesMB:    1024,
			Leaf: Leaf{
				Enabled:           false,
				HubDomain:         "hub",
				HubStream:         "LAB_READINGS",
				HubSubjectPrefix:  "lab",
				EnsureHubStream:   false,
				AckTimeoutSeconds: 10,
				RetryDelaySeconds: 5,
			},
		},
	}
}

// ---------------------------------------------------------------------------
// 派生取值

// LocalSubject 返回一条读数在边缘 JetStream 中的主题。
func (c Config) LocalSubject(code string) string {
	return fmt.Sprintf("%s.readings.%s", c.NATS.SubjectPrefix, SanitizeToken(code))
}

// LocalSubjectFilter 返回边缘读数流的主题通配。
func (c Config) LocalSubjectFilter() string {
	return c.NATS.SubjectPrefix + ".readings.>"
}

// HubSubject 返回一条读数在云端的主题：<prefix>.<site>.readings.<code>。
func (c Config) HubSubject(code string) string {
	return fmt.Sprintf("%s.%s.readings.%s",
		c.NATS.Leaf.HubSubjectPrefix, SanitizeToken(c.Agent.SiteID), SanitizeToken(code))
}

// HubSubjectFilter 返回云端读数流的主题通配。
func (c Config) HubSubjectFilter() string {
	return c.NATS.Leaf.HubSubjectPrefix + ".>"
}

// DataDir 返回数据目录的绝对路径。
func (c Config) DataDir() string {
	dir := c.Cache.Dir
	if dir == "" {
		dir = "data"
	}
	if abs, err := filepath.Abs(dir); err == nil {
		return abs
	}
	return dir
}

// JetStreamDir 返回 JetStream 存储目录。
func (c Config) JetStreamDir() string {
	if c.NATS.StoreDir != "" {
		if abs, err := filepath.Abs(c.NATS.StoreDir); err == nil {
			return abs
		}
		return c.NATS.StoreDir
	}
	return filepath.Join(c.DataDir(), "jetstream")
}

// PushTimeout 返回 HTTP 请求超时。
func (c Config) PushTimeout() time.Duration {
	return time.Duration(OrDefaultInt(c.Cloud.PushTimeoutSeconds, 10)) * time.Second
}

// PollInterval 返回云配置轮询间隔。
func (c Config) PollInterval() time.Duration {
	return time.Duration(OrDefaultInt(c.Cloud.ConfigPollSeconds, 10)) * time.Second
}

// EnabledInstruments 返回本地配置中启用的仪器清单。
//
// instruments 非空时用该列表；为空则回退旧的单仪器配置
// （agent.instrument_code + instrument.host/port）。
func (c Config) EnabledInstruments() []InstrumentEntry {
	out := make([]InstrumentEntry, 0, len(c.Instruments))
	for _, it := range c.Instruments {
		if !it.IsEnabled() || strings.TrimSpace(it.Code) == "" ||
			strings.TrimSpace(it.Host) == "" || it.Port <= 0 {
			continue
		}
		out = append(out, it)
	}
	if len(out) > 0 {
		return out
	}
	code := strings.TrimSpace(c.Agent.InstrumentCode)
	host := strings.TrimSpace(c.Instrument.Host)
	if code == "" || host == "" {
		return nil
	}
	port := c.Instrument.Port
	if port <= 0 {
		port = 9000
	}
	yes := true
	return []InstrumentEntry{{
		Code: code, Host: host, Port: port,
		Enabled: &yes, Push: &c.Agent.PushEnabled,
	}}
}

// SanitizeToken 把不适合做 NATS 主题 token 的字符替换掉
// （NATS 主题 token 不能含 . * > 与空白）。
func SanitizeToken(s string) string {
	s = strings.TrimSpace(s)
	if s == "" {
		return "unknown"
	}
	repl := strings.NewReplacer(".", "_", "*", "_", ">", "_", " ", "_", "\t", "_")
	return repl.Replace(s)
}

// OrDefaultInt 在 v 非正时返回 def。
func OrDefaultInt(v, def int) int {
	if v <= 0 {
		return def
	}
	return v
}

// ---------------------------------------------------------------------------
// Store：线程安全的配置容器（支持界面热更新与落盘）

// utf8BOM 是 UTF-8 字节序标记：Windows 上的编辑器与脚本常会写进 config.json。
var utf8BOM = []byte{0xEF, 0xBB, 0xBF}

// Store 持有当前配置，支持并发读取与增量更新。
type Store struct {
	mu   sync.RWMutex
	cfg  Config
	path string
}

// Load 从 path 读取配置；文件不存在时用默认值生成一份。
func Load(path string) (*Store, error) {
	if path == "" {
		path = "config.json"
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		abs = path
	}
	raw := map[string]any{}
	data, err := os.ReadFile(abs)
	switch {
	case err == nil:
		// 兼容 Windows 编辑器写入的 UTF-8 BOM
		data = bytes.TrimPrefix(data, utf8BOM)
		if len(strings.TrimSpace(string(data))) > 0 {
			if err := json.Unmarshal(data, &raw); err != nil {
				return nil, fmt.Errorf("解析配置 %s 失败: %w", abs, err)
			}
		}
	case os.IsNotExist(err):
		// 首次运行：留空，下面用默认值填充并落盘
	default:
		return nil, fmt.Errorf("读取配置 %s 失败: %w", abs, err)
	}

	cfg, err := merge(Defaults(), raw)
	if err != nil {
		return nil, err
	}
	s := &Store{cfg: cfg, path: abs}
	applyEnv(&s.cfg)
	if err := s.Save(); err != nil {
		return nil, err
	}
	return s, nil
}

// Get 返回配置快照（值拷贝，调用方可安全读取）。
func (s *Store) Get() Config {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.cfg
}

// Path 返回配置文件路径。
func (s *Store) Path() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.path
}

// Update 用界面提交的局部 JSON 深合并当前配置并落盘，返回新配置。
func (s *Store) Update(patch map[string]any) (Config, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	current, err := toMap(s.cfg)
	if err != nil {
		return s.cfg, err
	}
	deepMerge(current, patch)
	cfg, err := merge(Defaults(), current)
	if err != nil {
		return s.cfg, err
	}
	s.cfg = cfg
	return s.cfg, s.save()
}

// Save 原子落盘当前配置。
func (s *Store) Save() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.save()
}

func (s *Store) save() error {
	if dir := filepath.Dir(s.path); dir != "" {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return err
		}
	}
	data, err := json.MarshalIndent(s.cfg, "", "  ")
	if err != nil {
		return err
	}
	tmp := s.path + ".tmp"
	if err := os.WriteFile(tmp, append(data, '\n'), 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, s.path)
}

// ---------------------------------------------------------------------------
// 合并辅助

// merge 把 raw 中出现的键覆盖到 base 上（未出现的键保留默认值）。
func merge(base Config, raw map[string]any) (Config, error) {
	baseMap, err := toMap(base)
	if err != nil {
		return base, err
	}
	deepMerge(baseMap, raw)
	data, err := json.Marshal(baseMap)
	if err != nil {
		return base, err
	}
	var out Config
	if err := json.Unmarshal(data, &out); err != nil {
		return base, fmt.Errorf("配置结构不合法: %w", err)
	}
	return out, nil
}

func toMap(v any) (map[string]any, error) {
	data, err := json.Marshal(v)
	if err != nil {
		return nil, err
	}
	m := map[string]any{}
	if err := json.Unmarshal(data, &m); err != nil {
		return nil, err
	}
	return m, nil
}

// deepMerge 递归合并 src 到 dst；数组整体替换（如 instruments 清单）。
func deepMerge(dst, src map[string]any) {
	for k, sv := range src {
		if sm, ok := sv.(map[string]any); ok {
			if dm, ok := dst[k].(map[string]any); ok {
				deepMerge(dm, sm)
				continue
			}
		}
		dst[k] = sv
	}
}

// ---------------------------------------------------------------------------
// 环境变量覆盖（Docker 首次启动用；覆盖值会写入 config.json）

func applyEnv(c *Config) {
	envStr("LABGATE_HOST", &c.Agent.Host)
	envInt("LABGATE_PORT", &c.Agent.Port)
	envStr("LABGATE_MODE", &c.Agent.Mode)
	envStr("LABGATE_SITE_ID", &c.Agent.SiteID)
	envStr("LABGATE_API_TOKEN", &c.Agent.APIToken)
	envStr("LABGATE_DATA_DIR", &c.Cache.Dir)

	envStr("LABGATE_LIMS_URL", &c.Cloud.LIMSURL)
	envStr("LABGATE_LIMS_TOKEN", &c.Cloud.Token)
	envBool("LABGATE_LIMS_PUSH", &c.Cloud.LIMSPushEnabled)
	envBool("LABGATE_LIMS_POLL", &c.Cloud.PollEnabled)

	envStr("LABGATE_NATS_LISTEN", &c.NATS.Listen)
	envStr("LABGATE_NATS_MONITOR", &c.NATS.MonitorListen)
	envStr("LABGATE_NATS_STORE_DIR", &c.NATS.StoreDir)

	envBool("LABGATE_LEAF_ENABLED", &c.NATS.Leaf.Enabled)
	envStr("LABGATE_LEAF_URL", &c.NATS.Leaf.URL)
	envStr("LABGATE_LEAF_USER", &c.NATS.Leaf.User)
	envStr("LABGATE_LEAF_PASSWORD", &c.NATS.Leaf.Password)
	envStr("LABGATE_LEAF_CREDENTIALS", &c.NATS.Leaf.Credentials)
	envStr("LABGATE_LEAF_HUB_DOMAIN", &c.NATS.Leaf.HubDomain)
	envStr("LABGATE_LEAF_HUB_STREAM", &c.NATS.Leaf.HubStream)
	envBool("LABGATE_LEAF_ENSURE_HUB_STREAM", &c.NATS.Leaf.EnsureHubStream)

	// 填了 leaf url 就默认启用 LeafNode，省去再设一个开关
	if strings.TrimSpace(c.NATS.Leaf.URL) != "" {
		if _, set := os.LookupEnv("LABGATE_LEAF_ENABLED"); !set {
			c.NATS.Leaf.Enabled = true
		}
	}
}

func envStr(key string, dst *string) {
	if v, ok := os.LookupEnv(key); ok {
		*dst = v
	}
}

func envInt(key string, dst *int) {
	if v, ok := os.LookupEnv(key); ok {
		if n, err := strconv.Atoi(strings.TrimSpace(v)); err == nil {
			*dst = n
		}
	}
}

func envBool(key string, dst *bool) {
	if v, ok := os.LookupEnv(key); ok {
		if b, err := strconv.ParseBool(strings.TrimSpace(v)); err == nil {
			*dst = b
		}
	}
}
