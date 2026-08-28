// Package httpapi 提供本机管理界面与 JSON API。
//
// 路由与响应结构沿用旧 Python 采集端，这样云 LIMS 侧已有的调用
// （POST /api/start_sync、GET /api/state?code=xxx）无需改动即可对接。
package httpapi

import (
	"embed"
	"encoding/json"
	"fmt"
	"html/template"
	"io"
	"io/fs"
	"net/http"
	"strings"
	"time"

	"github.com/maitux/labgate/internal/acquire"
	"github.com/maitux/labgate/internal/bus"
	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/ingest"
	"github.com/maitux/labgate/internal/limspoll"
	"github.com/maitux/labgate/internal/logx"
	"github.com/maitux/labgate/internal/state"
)

//go:embed web
var webFS embed.FS

// pages 把路由映射到模板文件与导航高亮项。
var pages = []struct {
	route, file, active, title string
}{
	{"/", "index.html", "index", "采集"},
	{"/status", "status.html", "status", "状态"},
	{"/debug", "debug.html", "debug", "调试"},
	{"/config_page", "config.html", "config", "配置"},
	{"/logs", "logs.html", "logs", "日志"},
}

// Deps 是 HTTP 层依赖的各个组件。
type Deps struct {
	Config  *config.Store
	State   *state.State
	Log     *logx.Logger
	Acquire *acquire.Manager
	Ingest  *ingest.Ingestor
	Bus     *bus.Bus
	Poller  *limspoll.Poller
	Version string
}

// Server 是管理界面与 API 的处理器。
type Server struct {
	Deps
	tmpl map[string]*template.Template
}

// New 构造 Server 并预编译页面模板。
func New(d Deps) (*Server, error) {
	s := &Server{Deps: d, tmpl: map[string]*template.Template{}}
	for _, p := range pages {
		t, err := template.ParseFS(webFS, "web/layout.html", "web/"+p.file)
		if err != nil {
			return nil, fmt.Errorf("解析页面模板 %s 失败: %w", p.file, err)
		}
		s.tmpl[p.route] = t
	}
	return s, nil
}

// Handler 返回完整路由。
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()

	for _, p := range pages {
		route, active, title := p.route, p.active, p.title
		mux.HandleFunc("GET "+route, func(w http.ResponseWriter, r *http.Request) {
			s.renderPage(w, route, active, title)
		})
	}

	static, err := fs.Sub(webFS, "web/static")
	if err != nil {
		panic(err) // 编译期嵌入的目录，取不到说明构建有问题
	}
	mux.Handle("GET /static/", http.StripPrefix("/static/", http.FileServer(http.FS(static))))

	mux.HandleFunc("GET /healthz", s.handleHealth)
	mux.HandleFunc("GET /api/state", s.handleState)
	mux.HandleFunc("GET /api/readings", s.handleReadings)
	mux.HandleFunc("GET /api/logs", s.handleLogs)
	mux.HandleFunc("GET /api/stats", s.handleStats)
	mux.HandleFunc("GET /api/config", s.handleGetConfig)

	mux.HandleFunc("POST /api/config", s.handleSetConfig)
	mux.HandleFunc("POST /api/token/regenerate", s.handleRegenToken)
	mux.HandleFunc("POST /api/start", s.handleStart)
	mux.HandleFunc("POST /api/start_sync", s.handleStartSync)
	mux.HandleFunc("POST /api/stop", s.handleStop)
	mux.HandleFunc("POST /api/tcp_test", s.handleTCPTest)
	mux.HandleFunc("POST /api/http_test", s.handleInject)
	mux.HandleFunc("POST /api/parse_test", s.handleParseTest)
	mux.HandleFunc("POST /api/pull_now", s.handlePullNow)

	return s.auth(mux)
}

// auth 保护管理类写接口：配置了 agent.api_token 时，非豁免路径必须带
// Authorization: Bearer <token>（也兼容 X-API-Token 头）。
//
// 豁免路径是云 LIMS 联动的接口（LIMS 侧没有本机令牌）：/api/state、
// /api/start_sync。其余写接口（改配置、启停、注入读数、拉取）一律要求令牌。
// 未配置 api_token 时全部放行（兼容旧部署，界面会提示建议设置）。
func (s *Server) auth(next http.Handler) http.Handler {
	// 豁免：LIMS 联动接口（只读查询 / 同步启停）
	exempt := map[string]bool{
		"GET /api/state": true,
		"GET /api/readings": true,
		"GET /api/logs": true,
		"GET /api/stats": true,
		"GET /api/config": true,
		"POST /api/start_sync": true,
		"POST /api/stop": true, // LIMS 停止单台会话也走这里（带 code）
		"GET /healthz": true,
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := r.Method + " " + r.URL.Path
		if exempt[key] {
			next.ServeHTTP(w, r)
			return
		}
		token := s.Config.Get().Agent.APIToken
		if token == "" {
			// 未启用鉴权：放行（旧部署行为）
			next.ServeHTTP(w, r)
			return
		}
		got := strings.TrimSpace(r.Header.Get("Authorization"))
		got = strings.TrimPrefix(got, "Bearer ")
		got = strings.TrimSpace(got)
		if got == "" {
			got = strings.TrimSpace(r.Header.Get("X-API-Token"))
		}
		if got != token {
			writeJSON(w, http.StatusUnauthorized, map[string]any{
				"success": false,
				"message": "Invalid api_token（请在配置页设置或带 Authorization: Bearer <token>）",
			})
			return
		}
		next.ServeHTTP(w, r)
	})
}

// ---------------------------------------------------------------------------
// 通用辅助

func (s *Server) renderPage(w http.ResponseWriter, route, active, title string) {
	t := s.tmpl[route] // 路由与模板在 New 里成对注册，取不到说明是编码错误
	data := map[string]any{"Title": title, "Active": active, "Version": s.Version}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := t.ExecuteTemplate(w, "layout", data); err != nil {
		s.Log.Errorf("渲染页面 %s 失败：%v", route, err)
	}
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(data); err != nil {
		// 响应头已发出，这里只能记录
		_ = err
	}
}

func fail(w http.ResponseWriter, status int, format string, args ...any) {
	writeJSON(w, status, map[string]any{
		"success": false,
		"message": fmt.Sprintf(format, args...),
	})
}

// readJSON 解析请求体；空 body 视为空对象（旧采集端行为）。
func readJSON(r *http.Request, dst any) error {
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		return err
	}
	if len(body) == 0 {
		return nil
	}
	return json.Unmarshal(body, dst)
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"status":  "ok",
		"version": s.Version,
		"uptime":  time.Since(startedAt).Round(time.Second).String(),
	})
}

var startedAt = time.Now()
