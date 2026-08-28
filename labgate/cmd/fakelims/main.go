// fakelims 是一个替身 SENAITE：只实现 labgate/labbridge 用到的两个接口。
//
// 真的 maitux.instrument_acquisition 插件还在开发时，用它就能把整条链路
// 跑通、把"先称量后开始采集"的补投行为看清楚。
//
//	GET  /@@instrument_acquisition_api_agent_instruments   仪器清单与会话状态
//	POST /@@instrument_acquisition_api_ingest              收读数（无会话时 404）
//	GET  /                                                 一个小页面，可开关会话
//
// 行为刻意与插件保持一致：无监听会话返回 404 rejected，event_id 重复返回
// 200 duplicate。
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"html"
	"log"
	"net/http"
	"sort"
	"strings"
	"sync"
	"time"
)

type reading struct {
	EventID        string `json:"event_id"`
	SiteID         string `json:"site_id"`
	InstrumentCode string `json:"instrument_code"`
	ReceivedAt     string `json:"received_at"`
	RawText        string `json:"raw_text"`
	Parsed         struct {
		Value string `json:"value"`
		Unit  string `json:"unit"`
	} `json:"parsed"`
}

type store struct {
	mu        sync.Mutex
	listening map[string]bool
	seen      map[string]bool
	received  []reading
	rejected  int
}

func main() {
	listen := flag.String("listen", "0.0.0.0:8080", "监听地址")
	instruments := flag.String("instruments", "balance-01",
		"逗号分隔的仪器标识，会出现在仪器清单里")
	flag.Parse()

	s := &store{
		listening: map[string]bool{},
		seen:      map[string]bool{},
	}
	for _, code := range strings.Split(*instruments, ",") {
		if code = strings.TrimSpace(code); code != "" {
			s.listening[code] = false // 默认没有会话，模拟"还没点开始采集"
		}
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /@@instrument_acquisition_api_agent_instruments", s.handleInstruments)
	mux.HandleFunc("POST /@@instrument_acquisition_api_ingest", s.handleIngest)
	mux.HandleFunc("POST /session", s.handleToggle)
	mux.HandleFunc("GET /api/received", s.handleReceived)
	mux.HandleFunc("GET /", s.handlePage)

	log.Printf("替身 LIMS 已启动，监听 %s，仪器 %s", *listen, *instruments)
	srv := &http.Server{Addr: *listen, Handler: mux, ReadHeaderTimeout: 10 * time.Second}
	log.Fatal(srv.ListenAndServe())
}

func (s *store) handleInstruments(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	list := make([]map[string]any, 0, len(s.listening))
	for code, on := range s.listening {
		entry := map[string]any{"code": code, "start": on}
		if on {
			// 真插件在有会话时会带上仪器地址；桥接层用不到，这里给个占位
			entry["ip"] = "127.0.0.1"
			entry["port"] = 9000
		}
		list = append(list, entry)
	}
	s.mu.Unlock()
	sort.Slice(list, func(i, j int) bool {
		return list[i]["code"].(string) < list[j]["code"].(string)
	})
	writeJSON(w, 200, map[string]any{"instruments": list})
}

func (s *store) handleIngest(w http.ResponseWriter, r *http.Request) {
	var in reading
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.EventID == "" {
		writeJSON(w, 400, map[string]any{
			"success": false, "status": "rejected", "message": "Missing event_id",
		})
		return
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.listening[in.InstrumentCode] {
		s.rejected++
		writeJSON(w, 404, map[string]any{
			"success": false, "status": "rejected",
			"message": "No active listening session for instrument_code " + in.InstrumentCode,
		})
		return
	}
	if s.seen[in.EventID] {
		writeJSON(w, 200, map[string]any{
			"success": true, "status": "duplicate", "event_id": in.EventID,
		})
		return
	}
	s.seen[in.EventID] = true
	s.received = append(s.received, in)
	log.Printf("收下 [%s] %s = %s %s",
		in.InstrumentCode, in.RawText, in.Parsed.Value, in.Parsed.Unit)
	writeJSON(w, 200, map[string]any{
		"success": true, "status": "created", "event_id": in.EventID,
	})
}

func (s *store) handleToggle(w http.ResponseWriter, r *http.Request) {
	code := r.URL.Query().Get("code")
	start := r.URL.Query().Get("start") == "true"
	s.mu.Lock()
	if _, ok := s.listening[code]; !ok {
		s.mu.Unlock()
		writeJSON(w, 404, map[string]any{"success": false, "message": "未知仪器 " + code})
		return
	}
	s.listening[code] = start
	s.mu.Unlock()
	if start {
		log.Printf("[%s] 开始采集（会话已开）", code)
	} else {
		log.Printf("[%s] 停止采集（会话已关）", code)
	}
	writeJSON(w, 200, map[string]any{"success": true, "code": code, "start": start})
}

func (s *store) handleReceived(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := s.received
	if len(out) > 200 {
		out = out[len(out)-200:]
	}
	writeJSON(w, 200, map[string]any{
		"received": out, "total": len(s.received), "rejected": s.rejected,
	})
}

func (s *store) handlePage(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	codes := make([]string, 0, len(s.listening))
	for code := range s.listening {
		codes = append(codes, code)
	}
	sort.Strings(codes)
	listening := make(map[string]bool, len(s.listening))
	for k, v := range s.listening {
		listening[k] = v
	}
	total, rejected := len(s.received), s.rejected
	recent := s.received
	if len(recent) > 30 {
		recent = recent[len(recent)-30:]
	}
	rows := make([]string, 0, len(recent))
	for i := len(recent) - 1; i >= 0; i-- {
		r := recent[i]
		rows = append(rows, fmt.Sprintf(
			"<tr><td>%s</td><td>%s</td><td><code>%s</code></td><td><b>%s</b> %s</td></tr>",
			html.EscapeString(r.ReceivedAt), html.EscapeString(r.InstrumentCode),
			html.EscapeString(r.RawText), html.EscapeString(r.Parsed.Value),
			html.EscapeString(r.Parsed.Unit)))
	}
	s.mu.Unlock()

	buttons := make([]string, 0, len(codes))
	for _, code := range codes {
		state := "未采集"
		next := "true"
		if listening[code] {
			state = "采集中"
			next = "false"
		}
		buttons = append(buttons, fmt.Sprintf(
			`<p><b>%s</b> —— %s
			 <button onclick="toggle('%s','%s')">%s</button></p>`,
			html.EscapeString(code), state, html.EscapeString(code), next,
			map[string]string{"true": "开始采集", "false": "停止采集"}[next]))
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>替身 LIMS</title><meta http-equiv="refresh" content="3">
<style>body{font:14px -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
max-width:900px;margin:24px auto;padding:0 16px}
table{width:100%%;border-collapse:collapse}td,th{padding:6px 10px;
border-bottom:1px solid #ddd;text-align:left}code{color:#555}
button{padding:4px 12px;cursor:pointer}</style></head><body>
<h2>替身 LIMS（模拟 maitux.instrument_acquisition）</h2>
<p>已收下 <b>%d</b> 条，因无会话被拒 <b>%d</b> 次。</p>
%s
<p style="color:#666">试一下：先让仪器「未采集」跑一会儿（读数会堆在 NATS 里），
再点「开始采集」——之前那段时间的读数会被补投进来。</p>
<table><thead><tr><th>时间</th><th>仪器</th><th>原始行</th><th>解析值</th></tr></thead>
<tbody>%s</tbody></table>
<script>function toggle(code,start){
fetch('/session?code='+encodeURIComponent(code)+'&start='+start,{method:'POST'})
.then(function(){location.reload()});}</script>
</body></html>`, total, rejected, strings.Join(buttons, ""), strings.Join(rows, ""))
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
