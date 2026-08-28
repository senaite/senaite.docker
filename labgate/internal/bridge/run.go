package bridge

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"time"

	"github.com/maitux/labgate/internal/limsapi"
	"github.com/maitux/labgate/internal/logx"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

// Run 启动桥接服务并阻塞，直到 ctx 取消。
func Run(ctx context.Context, cfg Config, version string) error {
	log := logx.New(1000, slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})))

	if cfg.LIMS.URL == "" {
		return errors.New("未配置 lims.url（SENAITE 地址）")
	}

	nc, err := connect(cfg)
	if err != nil {
		return err
	}
	defer nc.Close()
	log.Infof("已连接云端 NATS %s", cfg.SafeNATSURL())

	js, err := newJetStream(nc, cfg)
	if err != nil {
		return err
	}

	// 流由云端或边缘的 ensure_hub_stream 创建；这里只做存在性检查，
	// 免得配错了流名之后一直静默无投递。
	checkCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
	_, err = js.Stream(checkCtx, cfg.NATS.Stream)
	cancel()
	if err != nil {
		return fmt.Errorf("云端读数流 %s 不可用: %w", cfg.NATS.Stream, err)
	}

	lims := limsapi.New(cfg.LIMS.URL, cfg.LIMS.Token, cfg.LIMSTimeout())
	b := New(js, lims, cfg.Options(), log)

	srv, listener, err := startHTTP(cfg, b, log, version)
	if err != nil {
		return err
	}
	defer srv.Close()

	fmt.Printf("\n  labbridge %s 已启动\n  云端 NATS  %s（流 %s）\n  SENAITE    %s\n  状态接口   http://%s/api/status\n  会话回溯   %s\n\n",
		version, cfg.SafeNATSURL(), cfg.NATS.Stream, cfg.LIMS.URL,
		listener.Addr(), cfg.Options().Lookback)

	errc := make(chan error, 1)
	go func() { errc <- b.Run(ctx) }()

	select {
	case <-ctx.Done():
		<-errc
		return nil
	case err := <-errc:
		return err
	}
}

func connect(cfg Config) (*nats.Conn, error) {
	opts := []nats.Option{
		nats.Name("labbridge"),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2 * time.Second),
		nats.Timeout(10 * time.Second),
	}
	switch {
	case cfg.NATS.Credentials != "":
		opts = append(opts, nats.UserCredentials(cfg.NATS.Credentials))
	case cfg.NATS.User != "":
		opts = append(opts, nats.UserInfo(cfg.NATS.User, cfg.NATS.Password))
	}
	if cfg.NATS.TLSInsecure {
		opts = append(opts, nats.Secure(&tls.Config{InsecureSkipVerify: true})) //nolint:gosec // 自签证书内网部署时按需打开
	}
	nc, err := nats.Connect(cfg.NATS.URL, opts...)
	if err != nil {
		return nil, fmt.Errorf("连接云端 NATS %s 失败: %w", cfg.SafeNATSURL(), err)
	}
	return nc, nil
}

func newJetStream(nc *nats.Conn, cfg Config) (jetstream.JetStream, error) {
	if cfg.NATS.Domain != "" {
		return jetstream.NewWithDomain(nc, cfg.NATS.Domain)
	}
	return jetstream.New(nc)
}

// startHTTP 起一个很小的状态接口：健康检查 + 各仪器投递情况。
func startHTTP(cfg Config, b *Bridge, log *logx.Logger, version string) (*http.Server, net.Listener, error) {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]any{"status": "ok", "version": version})
	})
	mux.HandleFunc("GET /api/status", func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		writeJSON(w, map[string]any{
			"version":          version,
			"stream":           cfg.NATS.Stream,
			"lims_url":         cfg.LIMS.URL,
			"lookback_minutes": cfg.Session.LookbackMinutes,
			"poll_error":       b.PollError(),
			"instruments":      b.Status(ctx),
		})
	})
	mux.HandleFunc("GET /api/logs", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]any{"logs": log.Snapshot(300)})
	})

	listen := cfg.HTTP.Listen
	if listen == "" {
		listen = "0.0.0.0:8091"
	}
	listener, err := net.Listen("tcp", listen)
	if err != nil {
		return nil, nil, fmt.Errorf("监听 %s 失败: %w", listen, err)
	}
	srv := &http.Server{Handler: mux, ReadHeaderTimeout: 10 * time.Second}
	go func() {
		if err := srv.Serve(listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Errorf("状态接口异常退出：%v", err)
		}
	}()
	return srv, listener, nil
}

func writeJSON(w http.ResponseWriter, data any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(data)
}
