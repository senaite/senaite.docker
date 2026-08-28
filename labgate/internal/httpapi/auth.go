package httpapi

// 管理界面的登录保护。
//
// 配了 agent.admin_password 就启用：网页跳 /login，管理接口返回 401 JSON。
// 登录后种一个签名 Cookie（HMAC，服务端不存会话），有效期 sessionTTL。
//
// 云 LIMS 联动的三个接口（/api/state、/api/start_sync、/api/stop）不参与，
// LIMS 侧只有 agent_token，不会也没法登录 —— 见 server.go 的 exempt 表。

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const (
	sessionCookie = "labgate_session"
	sessionTTL    = 12 * time.Hour
	// 密码错误时统一停顿一下，稍微抬高在线爆破的成本
	loginFailDelay = 300 * time.Millisecond
)

// credentials 返回管理界面的登录账号与是否启用登录。
// 密码为空 = 不启用（旧部署行为）；用户名缺省是 admin。
func (s *Server) credentials() (user, password string, enabled bool) {
	a := s.Config.Get().Agent
	user = strings.TrimSpace(a.AdminUser)
	if user == "" {
		user = "admin"
	}
	password = a.AdminPassword
	return user, password, password != ""
}

// sessionKey 由「进程密钥 + 当前账号密码」派生：
// 进程密钥保证 Cookie 不可离线伪造（密码本身可能很好猜），
// 掺进密码则让改密码后旧 Cookie 自动失效。
func (s *Server) sessionKey(user, password string) []byte {
	mac := hmac.New(sha256.New, s.secret)
	mac.Write([]byte(user))
	mac.Write([]byte{0})
	mac.Write([]byte(password))
	return mac.Sum(nil)
}

// signSession 生成 "<过期时间戳>.<签名>" 形式的 Cookie 值。
func (s *Server) signSession(user, password string, exp time.Time) string {
	payload := strconv.FormatInt(exp.Unix(), 10)
	mac := hmac.New(sha256.New, s.sessionKey(user, password))
	mac.Write([]byte(payload))
	return payload + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

// hasSessionCookie 校验请求里的会话 Cookie：签名对得上且没过期。
// 未启用登录时恒为 false —— 没有登录这回事，也就谈不上「已登录」。
func (s *Server) hasSessionCookie(r *http.Request) bool {
	user, password, enabled := s.credentials()
	if !enabled {
		return false
	}
	c, err := r.Cookie(sessionCookie)
	if err != nil {
		return false
	}
	payload, _, ok := strings.Cut(c.Value, ".")
	if !ok {
		return false
	}
	exp, err := strconv.ParseInt(payload, 10, 64)
	if err != nil || time.Now().Unix() > exp {
		return false
	}
	want := s.signSession(user, password, time.Unix(exp, 0))
	return subtle.ConstantTimeCompare([]byte(c.Value), []byte(want)) == 1
}

func (s *Server) setSession(w http.ResponseWriter, user, password string) {
	exp := time.Now().Add(sessionTTL)
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookie,
		Value:    s.signSession(user, password, exp),
		Path:     "/",
		Expires:  exp,
		MaxAge:   int(sessionTTL / time.Second),
		HttpOnly: true, // 页面脚本读不到，降低 XSS 顺手偷会话的风险
		SameSite: http.SameSiteLaxMode,
		// 不设 Secure：现场是内网 HTTP，设了 Cookie 根本种不上
	})
}

func clearSession(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookie,
		Value:    "",
		Path:     "/",
		MaxAge:   -1,
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
	})
}

// requireLogin 是最外层中间件：没登录的网页请求跳 /login，
// 接口请求返回 401 JSON（前端据此跳转）。
func (s *Server) requireLogin(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, _, enabled := s.credentials(); !enabled || loginExempt(r) || s.hasSessionCookie(r) {
			next.ServeHTTP(w, r)
			return
		}
		if strings.HasPrefix(r.URL.Path, "/api/") {
			writeJSON(w, http.StatusUnauthorized, map[string]any{
				"success":        false,
				"message":        "未登录或会话已过期，请重新登录",
				"login_required": true,
			})
			return
		}
		http.Redirect(w, r, "/login?next="+url.QueryEscape(r.URL.RequestURI()), http.StatusFound)
	})
}

// loginExempt 是不需要登录的路径：登录页自身、静态资源、健康检查，
// 以及云 LIMS 联动接口（这几个由 auth 的 exempt 表另行说明）。
func loginExempt(r *http.Request) bool {
	p := r.URL.Path
	if p == "/login" || p == "/logout" || p == "/healthz" || strings.HasPrefix(p, "/static/") {
		return true
	}
	return machineAPI[r.Method+" "+p]
}

// machineAPI 是云 LIMS 直接调用的接口：LIMS 侧不会登录，这几个必须放行。
var machineAPI = map[string]bool{
	"GET /api/state":       true,
	"POST /api/start_sync": true,
	"POST /api/stop":       true, // LIMS 停止单台会话也走这里（带 code）
}

// ---------------------------------------------------------------------------
// 登录页

func (s *Server) handleLoginPage(w http.ResponseWriter, r *http.Request) {
	if _, _, enabled := s.credentials(); !enabled {
		http.Redirect(w, r, "/", http.StatusFound)
		return
	}
	if s.hasSessionCookie(r) {
		http.Redirect(w, r, safeNext(r.URL.Query().Get("next")), http.StatusFound)
		return
	}
	s.renderLogin(w, http.StatusOK, "", r.URL.Query().Get("next"))
}

func (s *Server) handleLoginSubmit(w http.ResponseWriter, r *http.Request) {
	user, password, enabled := s.credentials()
	if !enabled {
		http.Redirect(w, r, "/", http.StatusFound)
		return
	}
	if err := r.ParseForm(); err != nil {
		s.renderLogin(w, http.StatusBadRequest, "表单解析失败", "")
		return
	}
	next := r.FormValue("next")
	gotUser := strings.TrimSpace(r.FormValue("user"))
	gotPass := r.FormValue("password")

	okUser := subtle.ConstantTimeCompare([]byte(gotUser), []byte(user)) == 1
	okPass := subtle.ConstantTimeCompare([]byte(gotPass), []byte(password)) == 1
	if !okUser || !okPass {
		time.Sleep(loginFailDelay)
		s.Log.Errorf("登录失败：账号 %q 来自 %s", gotUser, r.RemoteAddr)
		s.renderLogin(w, http.StatusUnauthorized, "账号或密码不对", next)
		return
	}

	s.setSession(w, user, password)
	s.Log.Infof("登录成功：%s（来自 %s）", user, r.RemoteAddr)
	http.Redirect(w, r, safeNext(next), http.StatusFound)
}

func (s *Server) handleLogout(w http.ResponseWriter, r *http.Request) {
	clearSession(w)
	http.Redirect(w, r, "/login", http.StatusFound)
}

func (s *Server) renderLogin(w http.ResponseWriter, status int, errMsg, next string) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	data := map[string]any{"Error": errMsg, "Next": safeNext(next), "Version": s.Version}
	if err := s.loginTmpl.Execute(w, data); err != nil {
		s.Log.Errorf("渲染登录页失败：%v", err)
	}
}

// safeNext 只接受本站绝对路径，挡掉 //evil.com 这类开放重定向。
func safeNext(next string) string {
	if next == "" || !strings.HasPrefix(next, "/") || strings.HasPrefix(next, "//") {
		return "/"
	}
	if next == "/login" || strings.HasPrefix(next, "/login?") {
		return "/"
	}
	return next
}

// newSecret 生成进程级签名密钥；进程重启即所有会话失效。
func newSecret() ([]byte, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return nil, fmt.Errorf("生成会话密钥失败: %w", err)
	}
	return b, nil
}
