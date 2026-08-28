// Package limsapi 封装与 SENAITE 插件 maitux.instrument_acquisition 的 HTTP 契约。
//
// 边缘（labgate）与云端桥接（labbridge）都用它，接口约定只有这一处定义：
//
//	GET  {lims}/@@instrument_acquisition_api_agent_instruments   仪器清单与启停指令
//	GET  {lims}/@@instrument_acquisition_api_agent_config        单台仪器（旧接口，回退用）
//	POST {lims}/@@instrument_acquisition_api_ingest              上报读数
package limsapi

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// SENAITE 插件的接口路径。
const (
	InstrumentsPath = "/@@instrument_acquisition_api_agent_instruments"
	AgentConfigPath = "/@@instrument_acquisition_api_agent_config"
	IngestPath      = "/@@instrument_acquisition_api_ingest"
)

// Instruction 是 LIMS 对一台仪器下发的采集指令。
//
// Start 为真表示该仪器在 LIMS 侧有"监听中的会话"，也就是有人点了「开始采集」。
// 桥接层用它判断读数现在能不能被 LIMS 收下。
type Instruction struct {
	Code      string `json:"code"`
	Start     bool   `json:"start"`
	IP        string `json:"ip"`
	Port      int    `json:"port"`
	SessionID string `json:"session_id,omitempty"`
	Operator  string `json:"operator,omitempty"`
	Reason    string `json:"reason,omitempty"`
}

// Outcome 是一次上报读数的结果分类。
type Outcome int

const (
	// Accepted：LIMS 收下了（created 或 duplicate，后者说明幂等去重生效）。
	Accepted Outcome = iota
	// NoSession：该仪器当前没有监听中的会话（404 / 409）。
	// 读数本身没问题，等会话开起来再投就能进——不该丢，也不该盲目重试。
	NoSession
	// Rejected：LIMS 明确拒绝且重投无用（如缺 event_id）。
	Rejected
	// Transient：网络故障、5xx、401 等，稍后重试有机会成功。
	Transient
)

func (o Outcome) String() string {
	switch o {
	case Accepted:
		return "accepted"
	case NoSession:
		return "no-session"
	case Rejected:
		return "rejected"
	default:
		return "transient"
	}
}

// Result 是一次上报的完整结果。
type Result struct {
	Outcome Outcome
	Status  int
	Message string
}

// Client 是 SENAITE 接口的 HTTP 客户端。
type Client struct {
	// BaseURL 是 LIMS 地址，如 http://lims.example.com:8080/lims
	BaseURL string
	// Token 会作为 X-Instrument-Token 请求头发送。
	Token string
	// Timeout 是单次请求的超时。
	Timeout time.Duration

	HTTP *http.Client
}

// New 构造客户端。
func New(baseURL, token string, timeout time.Duration) *Client {
	if timeout <= 0 {
		timeout = 10 * time.Second
	}
	return &Client{
		BaseURL: baseURL,
		Token:   token,
		Timeout: timeout,
		// 单请求超时由 context 控制，这里留一个兜底上限
		HTTP: &http.Client{Timeout: 2 * time.Minute},
	}
}

// Configured 返回是否填了 LIMS 地址。
func (c *Client) Configured() bool { return strings.TrimSpace(c.BaseURL) != "" }

// Instruments 拉取本站负责的全部仪器及其启停状态。
func (c *Client) Instruments(ctx context.Context) ([]Instruction, error) {
	body, _, err := c.get(ctx, c.endpoint(InstrumentsPath))
	if err != nil {
		return nil, err
	}
	var out struct {
		Instruments []Instruction `json:"instruments"`
	}
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, fmt.Errorf("解析仪器清单失败: %w", err)
	}
	if out.Instruments == nil {
		return nil, errors.New("响应中没有 instruments 字段")
	}
	return out.Instruments, nil
}

// AgentConfig 拉取单台仪器的配置（旧接口，LIMS 没有 instruments 接口时回退用）。
func (c *Client) AgentConfig(ctx context.Context, code string) (Instruction, error) {
	endpoint := c.endpoint(AgentConfigPath) + "?" +
		url.Values{"instrument_code": {code}}.Encode()
	body, _, err := c.get(ctx, endpoint)
	if err != nil {
		return Instruction{}, err
	}
	var ins Instruction
	if err := json.Unmarshal(body, &ins); err != nil {
		return Instruction{}, fmt.Errorf("解析仪器配置失败: %w", err)
	}
	ins.Code = code
	return ins, nil
}

// Ingest 上报一条读数，payload 是 model.Reading 的 JSON。
func (c *Client) Ingest(ctx context.Context, payload []byte) Result {
	reqCtx, cancel := context.WithTimeout(ctx, c.Timeout)
	defer cancel()

	req, err := http.NewRequestWithContext(reqCtx, http.MethodPost,
		c.endpoint(IngestPath), bytes.NewReader(payload))
	if err != nil {
		return Result{Outcome: Rejected, Message: err.Error()}
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Instrument-Token", c.Token)

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return Result{Outcome: Transient, Message: err.Error()}
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
	return classify(resp.StatusCode, body)
}

// classify 把 SENAITE 的响应归到四类结果里。
//
// 状态码含义来自插件 api/views.py 的 IngestReadingAPI：
//
//	200 + success:true   收下（created / duplicate）
//	404                  该仪器没有监听中的会话 / 按 session_id 找不到会话
//	409                  会话存在但未在监听，或仪器不匹配
//	401                  Token 不对——改配置后能恢复，算临时故障
//	其余 4xx             请求本身有问题，重投无用
func classify(status int, body []byte) Result {
	msg := snippet(body)
	switch {
	case status >= 200 && status < 300:
		var out struct {
			Success bool   `json:"success"`
			Status  string `json:"status"`
		}
		if err := json.Unmarshal(body, &out); err == nil && out.Success {
			return Result{Outcome: Accepted, Status: status, Message: out.Status}
		}
		// 2xx 但 success 不为真：当作临时故障重试，避免误丢数据
		return Result{Outcome: Transient, Status: status, Message: msg}

	case status == http.StatusNotFound, status == http.StatusConflict:
		return Result{Outcome: NoSession, Status: status, Message: msg}

	case status == http.StatusUnauthorized:
		// LIMS 明确拒绝该条消息：token 与 instrument_code 的组合不被接受
		// （多为仪器 code 在 LIMS 侧无解析模板）。归为 Rejected 做有界重试，
		// 5 次后放弃，避免一条永远推不进的消息无限刷屏。
		// 若只是临时配错 token，改配置后 5 次重试内（约 25 秒）即恢复。
		return Result{Outcome: Rejected, Status: status, Message: msg}

	case status == http.StatusRequestTimeout,
		status == http.StatusTooManyRequests:
		return Result{Outcome: Transient, Status: status, Message: msg}

	case status >= 400 && status < 500:
		return Result{Outcome: Rejected, Status: status, Message: msg}

	default:
		return Result{Outcome: Transient, Status: status, Message: msg}
	}
}

func (c *Client) endpoint(path string) string {
	return strings.TrimRight(c.BaseURL, "/") + path
}

func (c *Client) get(ctx context.Context, endpoint string) ([]byte, int, error) {
	reqCtx, cancel := context.WithTimeout(ctx, c.Timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(reqCtx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("X-Instrument-Token", c.Token)
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, resp.StatusCode, fmt.Errorf("HTTP %d: %s", resp.StatusCode, snippet(body))
	}
	return body, resp.StatusCode, nil
}

func snippet(body []byte) string {
	s := strings.TrimSpace(string(body))
	if len(s) > 200 {
		return s[:200] + "..."
	}
	return s
}
