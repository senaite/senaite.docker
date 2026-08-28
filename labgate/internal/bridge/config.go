package bridge

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// NATSConfig 是连接云端 NATS 的参数（桥接层是普通客户端，不是 LeafNode）。
type NATSConfig struct {
	URL         string `json:"url"` // nats://hub:4222
	User        string `json:"user"`
	Password    string `json:"password"`
	Credentials string `json:"credentials"`
	// Domain 是云端 JetStream 域；桥接与云端 NATS 直连时通常留空即可，
	// 只有云端本身也被划进某个域时才需要填。
	Domain        string `json:"domain"`
	Stream        string `json:"stream"`
	SubjectPrefix string `json:"subject_prefix"`
	TLSInsecure   bool   `json:"tls_insecure"`
}

// LIMSConfig 是 SENAITE 的地址与凭证。
type LIMSConfig struct {
	URL            string `json:"url"`
	Token          string `json:"token"`
	TimeoutSeconds int    `json:"timeout_seconds"`
}

// SessionConfig 决定"会话开始前的读数要不要补投、补多久"。
//
// LookbackMinutes 是这里最需要业务上拍板的一个数：技术员先称量、
// 隔多久之内再点「开始采集」，之前的读数还算数？设为 0 表示不补投，
// 只投会话开始之后的读数。
type SessionConfig struct {
	LookbackMinutes   int `json:"lookback_minutes"`
	PollSeconds       int `json:"poll_seconds"`
	RetryDelaySeconds int `json:"retry_delay_seconds"`
	MaxAckPending     int `json:"max_ack_pending"`
}

// HTTPConfig 是桥接自身的状态接口。
type HTTPConfig struct {
	Listen string `json:"listen"`
}

// Config 是桥接层的完整配置。
type Config struct {
	NATS    NATSConfig    `json:"nats"`
	LIMS    LIMSConfig    `json:"lims"`
	Session SessionConfig `json:"session"`
	HTTP    HTTPConfig    `json:"http"`
}

// Defaults 返回默认配置。
func Defaults() Config {
	return Config{
		NATS: NATSConfig{
			URL:           "nats://127.0.0.1:4222",
			Stream:        "LAB_READINGS",
			SubjectPrefix: "lab",
		},
		LIMS: LIMSConfig{TimeoutSeconds: 10},
		Session: SessionConfig{
			// 15 分钟：够覆盖"先称量、后点开始采集"，又不会把更早的
			// 陈年读数一起灌进 LIMS。按实际工作流调整。
			LookbackMinutes:   15,
			PollSeconds:       10,
			RetryDelaySeconds: 5,
			MaxAckPending:     64,
		},
		HTTP: HTTPConfig{Listen: "0.0.0.0:8091"},
	}
}

// Options 把配置换算成运行参数。
func (c Config) Options() Options {
	return Options{
		Stream:         c.NATS.Stream,
		SubjectPrefix:  c.NATS.SubjectPrefix,
		Lookback:       time.Duration(c.Session.LookbackMinutes) * time.Minute,
		PollInterval:   time.Duration(orDefault(c.Session.PollSeconds, 10)) * time.Second,
		RetryDelay:     time.Duration(orDefault(c.Session.RetryDelaySeconds, 5)) * time.Second,
		MaxAckPending:  orDefault(c.Session.MaxAckPending, 64),
		ConsumerPrefix: "bridge",
	}
}

// LIMSTimeout 返回 HTTP 请求超时。
func (c Config) LIMSTimeout() time.Duration {
	return time.Duration(orDefault(c.LIMS.TimeoutSeconds, 10)) * time.Second
}

// LoadConfig 读取配置文件；不存在时用默认值生成一份。
func LoadConfig(path string) (Config, error) {
	if path == "" {
		path = "bridge.json"
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		abs = path
	}

	raw := map[string]any{}
	data, err := os.ReadFile(abs)
	switch {
	case err == nil:
		data = bytes.TrimPrefix(data, []byte{0xEF, 0xBB, 0xBF}) // Windows 编辑器的 BOM
		if len(bytes.TrimSpace(data)) > 0 {
			if err := json.Unmarshal(data, &raw); err != nil {
				return Config{}, fmt.Errorf("解析配置 %s 失败: %w", abs, err)
			}
		}
	case os.IsNotExist(err):
		// 首次运行：用默认值生成
	default:
		return Config{}, fmt.Errorf("读取配置 %s 失败: %w", abs, err)
	}

	cfg, err := merge(Defaults(), raw)
	if err != nil {
		return Config{}, err
	}
	applyEnv(&cfg)

	out, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return Config{}, err
	}
	if err := os.WriteFile(abs, append(out, '\n'), 0o644); err != nil {
		return Config{}, fmt.Errorf("写入配置 %s 失败: %w", abs, err)
	}
	return cfg, nil
}

func merge(base Config, raw map[string]any) (Config, error) {
	data, err := json.Marshal(base)
	if err != nil {
		return base, err
	}
	baseMap := map[string]any{}
	if err := json.Unmarshal(data, &baseMap); err != nil {
		return base, err
	}
	deepMerge(baseMap, raw)
	merged, err := json.Marshal(baseMap)
	if err != nil {
		return base, err
	}
	var out Config
	if err := json.Unmarshal(merged, &out); err != nil {
		return base, fmt.Errorf("配置结构不合法: %w", err)
	}
	return out, nil
}

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

// applyEnv 让容器部署可以只用环境变量起服务。
func applyEnv(c *Config) {
	envStr("LABBRIDGE_NATS_URL", &c.NATS.URL)
	envStr("LABBRIDGE_NATS_USER", &c.NATS.User)
	envStr("LABBRIDGE_NATS_PASSWORD", &c.NATS.Password)
	envStr("LABBRIDGE_NATS_CREDENTIALS", &c.NATS.Credentials)
	envStr("LABBRIDGE_NATS_DOMAIN", &c.NATS.Domain)
	envStr("LABBRIDGE_STREAM", &c.NATS.Stream)
	envStr("LABBRIDGE_SUBJECT_PREFIX", &c.NATS.SubjectPrefix)

	envStr("LABBRIDGE_LIMS_URL", &c.LIMS.URL)
	envStr("LABBRIDGE_LIMS_TOKEN", &c.LIMS.Token)

	envInt("LABBRIDGE_LOOKBACK_MINUTES", &c.Session.LookbackMinutes)
	envInt("LABBRIDGE_POLL_SECONDS", &c.Session.PollSeconds)
	envStr("LABBRIDGE_HTTP_LISTEN", &c.HTTP.Listen)
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

func orDefault(v, def int) int {
	if v <= 0 {
		return def
	}
	return v
}

// SafeNATSURL 返回抹掉密码的 NATS 地址，供日志与状态接口使用。
func (c Config) SafeNATSURL() string {
	raw := c.NATS.URL
	at := strings.LastIndex(raw, "@")
	scheme := strings.Index(raw, "://")
	if at < 0 || scheme < 0 || at < scheme {
		return raw
	}
	userinfo := raw[scheme+3 : at]
	if colon := strings.Index(userinfo, ":"); colon >= 0 {
		userinfo = userinfo[:colon]
	}
	return raw[:scheme+3] + userinfo + raw[at:]
}
