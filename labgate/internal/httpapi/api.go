package httpapi

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/maitux/labgate/internal/acquire"
	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/parse"
	"github.com/maitux/labgate/internal/state"
)

// stateResponse 是 /api/state 的响应。
//
// 前若干字段保持旧采集端的结构（云 LIMS 会读 connected / current_host 等），
// cloud、site_id、version 是新增字段，旧调用方会忽略。
type stateResponse struct {
	Mode        string `json:"mode"`
	SiteID      string `json:"site_id"`
	Connected   bool   `json:"connected"`
	Connecting  bool   `json:"connecting"`
	LastMessage string `json:"last_message"`
	CurrentHost string `json:"current_host"`
	CurrentPort int    `json:"current_port"`

	Stats       state.Stats        `json:"stats"`
	Config      config.Config      `json:"config"`
	Instruments []acquire.Snapshot `json:"instruments"`

	CloudLastPull  map[string]any    `json:"cloud_last_pull"`
	CloudLastError string            `json:"cloud_last_error"`
	Cloud          state.CloudStatus `json:"cloud"`
	Version        string            `json:"version"`
}

func (s *Server) handleState(w http.ResponseWriter, r *http.Request) {
	cfg := s.Config.Get()
	instruments := s.Acquire.States()
	pull, pullErr := s.State.CloudPull()
	_, leafErr, lastForward := s.State.Leaf()

	resp := stateResponse{
		Mode:           cfg.Agent.Mode,
		SiteID:         cfg.Agent.SiteID,
		Stats:          s.State.Stats(),
		Config:         redact(cfg),
		Instruments:    instruments,
		CloudLastPull:  pull,
		CloudLastError: pullErr,
		Version:        s.Version,
		Cloud: state.CloudStatus{
			LeafEnabled:   cfg.NATS.Leaf.Enabled,
			LeafConnected: s.Bus.LeafConnected(),
			LeafURL:       cfg.NATS.Leaf.SafeURL(),
			HubStream:     cfg.NATS.Leaf.HubStream,
			LastError:     leafErr,
			LastForwardAt: lastForward,
			Pending:       s.State.Pending(),
		},
	}

	// ?code=xxx：返回指定仪器的连接状态（云 LIMS 按仪器查询时用）
	if code := strings.TrimSpace(r.URL.Query().Get("code")); code != "" {
		if snap, ok := s.Acquire.Snapshot(code); ok {
			resp.Connected = snap.Connected
			resp.Connecting = snap.Connecting
			resp.LastMessage = snap.LastMessage
			resp.CurrentHost = snap.CurrentHost
			resp.CurrentPort = snap.CurrentPort
		} else {
			// auto 模式：仪器清单由云 LIMS 下发。只要 cloud_last_pull
			// 里出现过该仪器，就说明 LIMS 侧已登记，只是还没下发「开始采集」。
			if _, known := pull[code]; known {
				resp.LastMessage = "已登记，等待 LIMS 开始采集"
			} else {
				resp.LastMessage = "该仪器未在本采集端登记"
			}
		}
		writeJSON(w, http.StatusOK, resp)
		return
	}

	// 不带 code：多仪器汇总，任一连接即视为已连接
	messages := make([]string, 0, len(instruments))
	for _, it := range instruments {
		if it.Connected {
			resp.Connected = true
			if resp.CurrentHost == "" {
				resp.CurrentHost, resp.CurrentPort = it.CurrentHost, it.CurrentPort
			}
		}
		if it.Connecting {
			resp.Connecting = true
		}
		messages = append(messages, fmt.Sprintf("[%s] %s", it.Code, it.LastMessage))
	}
	resp.LastMessage = strings.Join(messages, "；")
	if resp.LastMessage == "" {
		resp.LastMessage = "未连接任何仪器"
	}
	writeJSON(w, http.StatusOK, resp)
}

func (s *Server) handleReadings(w http.ResponseWriter, r *http.Request) {
	limit := 200
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			limit = n
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"readings": s.State.Readings(limit)})
}

func (s *Server) handleLogs(w http.ResponseWriter, r *http.Request) {
	limit := 300
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			limit = n
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"logs": s.Log.Snapshot(limit)})
}

func (s *Server) handleStats(w http.ResponseWriter, r *http.Request) {
	cfg := s.Config.Get()
	stats := s.State.Stats()

	out := map[string]any{
		// cache 段保持旧字段名，界面与既有脚本可以直接读
		"cache": map[string]any{
			"pending": stats.CachePending,
			"done":    stats.PushOK,
			"dropped": stats.PushFail,
		},
		"state":       stats,
		"instruments": s.Acquire.States(),
		"store_dir":   cfg.JetStreamDir(),
	}

	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()
	if stream, err := s.Bus.LocalJS().Stream(ctx, streamName(cfg)); err == nil {
		if info, err := stream.Info(ctx); err == nil {
			out["stream"] = map[string]any{
				"name":      info.Config.Name,
				"messages":  info.State.Msgs,
				"bytes":     info.State.Bytes,
				"first_seq": info.State.FirstSeq,
				"last_seq":  info.State.LastSeq,
				"consumers": info.State.Consumers,
			}
		}
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) handleGetConfig(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, s.Config.Get())
}

func (s *Server) handleSetConfig(w http.ResponseWriter, r *http.Request) {
	patch := map[string]any{}
	if err := readJSON(r, &patch); err != nil {
		fail(w, http.StatusBadRequest, "请求体不是合法 JSON：%v", err)
		return
	}
	before := s.Config.Get()
	cfg, err := s.Config.Update(patch)
	if err != nil {
		fail(w, http.StatusInternalServerError, "保存配置失败：%v", err)
		return
	}
	s.State.SetMode(cfg.Agent.Mode)
	s.Log.Infof("配置已更新")

	writeJSON(w, http.StatusOK, map[string]any{
		"success":          true,
		"config":           cfg,
		"restart_required": natsChanged(before, cfg),
	})
}

// natsChanged 判断改动是否需要重启才能生效。
// 内嵌 NATS 的监听地址、JetStream 域与 LeafNode 连接都是启动时确定的。
func natsChanged(before, after config.Config) bool {
	return before.NATS.Listen != after.NATS.Listen ||
		before.NATS.MonitorListen != after.NATS.MonitorListen ||
		before.NATS.Domain != after.NATS.Domain ||
		before.NATS.StoreDir != after.NATS.StoreDir ||
		before.NATS.Leaf != after.NATS.Leaf
}

func (s *Server) handleRegenToken(w http.ResponseWriter, r *http.Request) {
	buf := make([]byte, 24)
	if _, err := rand.Read(buf); err != nil {
		fail(w, http.StatusInternalServerError, "生成 Token 失败：%v", err)
		return
	}
	token := base64.RawURLEncoding.EncodeToString(buf)
	if _, err := s.Config.Update(map[string]any{
		"cloud": map[string]any{"token": token},
	}); err != nil {
		fail(w, http.StatusInternalServerError, "保存 Token 失败：%v", err)
		return
	}
	s.Log.Infof("Token 已重新生成")
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "token": token})
}

// startRequest 是 /api/start 与 /api/start_sync 的请求体。
type startRequest struct {
	Code string `json:"code"`
	Host string `json:"host"`
	Port any    `json:"port"` // 兼容旧调用方把端口写成字符串
	Push *bool  `json:"push"`
}

func (s *Server) parseStart(r *http.Request) (code, host string, port int, push bool, err error) {
	var req startRequest
	if err = readJSON(r, &req); err != nil {
		return "", "", 0, false, fmt.Errorf("请求体不是合法 JSON：%w", err)
	}
	host = strings.TrimSpace(req.Host)
	if host == "" {
		return "", "", 0, false, fmt.Errorf("请填写仪器 IP")
	}
	port, err = toPort(req.Port)
	if err != nil {
		return "", "", 0, false, err
	}
	push = true
	if req.Push != nil {
		push = *req.Push
	}
	code = strings.TrimSpace(req.Code)
	if code == "" {
		code = s.resolveCode(host, port)
	}
	return code, host, port, push, nil
}

// resolveCode 按 host:port 反查 instrument_code。
//
// 顺序：本地配置仪器清单 → 最近一轮云 LIMS 轮询结果（auto 模式，LIMS
// 下发过 ip/port 的仪器）→ agent.instrument_code 兜底。
// 找不到时返回空串（调用方会按请求原样处理，不硬编码假 code）。
func (s *Server) resolveCode(host string, port int) string {
	cfg := s.Config.Get()
	for _, inst := range cfg.EnabledInstruments() {
		if inst.Host == host && inst.Port == port {
			return inst.Code
		}
	}
	// auto 模式：LIMS 下发的仪器清单里有 ip/port，按目标反查真实 code。
	// 这避免 LIMS 用旧版协议（start_sync 不带 code）时，
	// 本网关建一个 code=instrument 的错误连接，导致读数推不进 LIMS。
	if pull, _ := s.State.CloudPull(); pull != nil {
		for code, v := range pull {
			m, ok := v.(map[string]any)
			if !ok {
				continue
			}
			ip, _ := m["ip"].(string)
			p, _ := m["port"].(float64)
			if ip == host && int(p) == port {
				return code
			}
		}
	}
	if code := strings.TrimSpace(cfg.Agent.InstrumentCode); code != "" {
		return code
	}
	return ""
}

func (s *Server) handleStart(w http.ResponseWriter, r *http.Request) {
	code, host, port, push, err := s.parseStart(r)
	if err != nil {
		fail(w, http.StatusBadRequest, "%v", err)
		return
	}
	s.Acquire.Start(code, host, port, push)
	s.Log.Infof("手动开始采集 [%s] %s:%d（上传=%t）", code, host, port, push)
	writeJSON(w, http.StatusOK, map[string]any{"success": true})
}

// handleStartSync 同步开始采集：先探测 TCP 通道，探不通立即返回失败。
//
// 云 LIMS 的「开始采集」按钮调用这个接口，好让操作员当场看到
// "天平没开机 / 地址不对"，而不是先显示成功再默默重试。
func (s *Server) handleStartSync(w http.ResponseWriter, r *http.Request) {
	code, host, port, push, err := s.parseStart(r)
	if err != nil {
		fail(w, http.StatusBadRequest, "%v", err)
		return
	}
	addr := net.JoinHostPort(host, strconv.Itoa(port))
	conn, dialErr := net.DialTimeout("tcp", addr, 3*time.Second)
	if dialErr != nil {
		s.Log.Warnf("同步开始采集失败：连接 %s 失败：%v", addr, dialErr)
		// 与旧采集端一致：HTTP 200 + success:false，由 LIMS 展示 message
		writeJSON(w, http.StatusOK, map[string]any{
			"success": false,
			"message": fmt.Sprintf("连接仪器 %s 失败：%v", addr, dialErr),
		})
		return
	}
	_ = conn.Close()

	// 无法确定仪器 code 时拒绝开始，避免建一个 code="" 或假的连接：
	// 读数会推不进 LIMS（校验按 instrument_code 反查模板）。
	if code == "" {
		writeJSON(w, http.StatusOK, map[string]any{
			"success": false,
			"message": "无法确定仪器 code（请带 code，或等 LIMS 轮询下发仪器清单）",
		})
		return
	}

	s.Acquire.Start(code, host, port, push)
	s.Log.Infof("同步开始采集 [%s] %s（上传=%t）", code, addr, push)
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"message": fmt.Sprintf("已连接 %s", addr),
	})
}

func (s *Server) handleStop(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Code string `json:"code"`
		All  bool   `json:"all"`
	}
	if err := readJSON(r, &req); err != nil {
		fail(w, http.StatusBadRequest, "请求体不是合法 JSON：%v", err)
		return
	}
	code := strings.TrimSpace(req.Code)
	if code == "" && !req.All {
		// S2 防御：空 body 不再静默停全部（曾导致 LIMS 停一台、全站仪器全停）。
		// 停全部必须显式 all=true；LIMS 停单台带 code。
		fail(w, http.StatusBadRequest,
			"请指定要停止的仪器 code，或显式传 {\"all\": true} 停止全部")
		return
	}
	s.Acquire.Stop(code)
	if code == "" {
		s.Log.Infof("停止采集（全部）")
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true})
}

func (s *Server) handleTCPTest(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Host string `json:"host"`
		Port any    `json:"port"`
	}
	if err := readJSON(r, &req); err != nil {
		fail(w, http.StatusBadRequest, "请求体不是合法 JSON：%v", err)
		return
	}
	host := strings.TrimSpace(req.Host)
	port, err := toPort(req.Port)
	if err != nil || host == "" {
		fail(w, http.StatusBadRequest, "请填写有效的 IP 和端口")
		return
	}
	addr := net.JoinHostPort(host, strconv.Itoa(port))
	conn, err := net.DialTimeout("tcp", addr, 3*time.Second)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"success": false,
			"message": fmt.Sprintf("TCP 连接失败：%v", err),
		})
		return
	}
	_ = conn.Close()
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"message": "TCP 连接成功：" + addr,
	})
}

// handleInject 注入一条读数，走完整链路（解析 → 落盘 → 转发）。
// 路径沿用旧采集端的 /api/http_test。
func (s *Server) handleInject(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RawText string `json:"raw_text"`
		Code    string `json:"code"`
	}
	if err := readJSON(r, &req); err != nil {
		fail(w, http.StatusBadRequest, "请求体不是合法 JSON：%v", err)
		return
	}
	raw := strings.TrimSpace(req.RawText)
	if raw == "" {
		fail(w, http.StatusBadRequest, "请输入一条读数")
		return
	}
	code := strings.TrimSpace(req.Code)
	if code == "" {
		code = strings.TrimSpace(s.Config.Get().Agent.InstrumentCode)
	}
	if code == "" {
		code = "instrument"
	}

	value, unit := parse.Reading(raw)
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	reading, err := s.Ingest.Submit(ctx, code, raw, value, unit, true)
	if err != nil {
		fail(w, http.StatusInternalServerError, "落盘失败：%v", err)
		return
	}
	s.Log.Infof("调试注入一条读数 [%s] %s", code, raw)
	writeJSON(w, http.StatusOK, map[string]any{
		"success":  true,
		"message":  "已落盘，转发器会自动上云",
		"event_id": reading.EventID,
		"parsed":   map[string]any{"value": value, "unit": unit},
	})
}

func (s *Server) handleParseTest(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RawText string `json:"raw_text"`
	}
	if err := readJSON(r, &req); err != nil {
		fail(w, http.StatusBadRequest, "请求体不是合法 JSON：%v", err)
		return
	}
	value, unit := parse.Reading(req.RawText)
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"parsed":  map[string]any{"value": value, "unit": unit},
	})
}

func (s *Server) handlePullNow(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	result, err := s.Poller.PullOnce(ctx)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"success": false,
			"message": err.Error(),
		})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "config": result})
}

// ---------------------------------------------------------------------------

// toPort 接受数字或字符串形式的端口（旧调用方两种都发过）。
func toPort(v any) (int, error) {
	switch p := v.(type) {
	case float64:
		if p <= 0 || p > 65535 {
			return 0, fmt.Errorf("端口无效")
		}
		return int(p), nil
	case string:
		n, err := strconv.Atoi(strings.TrimSpace(p))
		if err != nil || n <= 0 || n > 65535 {
			return 0, fmt.Errorf("端口无效")
		}
		return n, nil
	case nil:
		return 0, fmt.Errorf("请填写端口")
	default:
		return 0, fmt.Errorf("端口无效")
	}
}

// redact 屏蔽 /api/state 里的凭据 —— 这个接口会被云 LIMS 反复轮询。
// 配置页读的是 /api/config，那里仍返回原值。
func redact(cfg config.Config) config.Config {
	if cfg.Cloud.Token != "" {
		cfg.Cloud.Token = "***"
	}
	if cfg.NATS.Leaf.Password != "" {
		cfg.NATS.Leaf.Password = "***"
	}
	cfg.NATS.Leaf.URL = cfg.NATS.Leaf.SafeURL()
	return cfg
}

func streamName(cfg config.Config) string {
	if cfg.NATS.Stream == "" {
		return "READINGS"
	}
	return cfg.NATS.Stream
}
