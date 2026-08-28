// Package app 把各个组件装配成一个可运行的采集端。
//
// 启动顺序：配置 → 内嵌 NATS/JetStream → 落盘器 → 采集管理器 →
// 转发器与轮询器 → HTTP 界面。关闭时反向进行，先停采集再收尾。
package app

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"

	"github.com/maitux/labgate/internal/acquire"
	"github.com/maitux/labgate/internal/bus"
	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/forward"
	"github.com/maitux/labgate/internal/httpapi"
	"github.com/maitux/labgate/internal/ingest"
	"github.com/maitux/labgate/internal/limspoll"
	"github.com/maitux/labgate/internal/logx"
	"github.com/maitux/labgate/internal/state"
)

// Options 是命令行传入的启动参数（优先级高于配置文件）。
type Options struct {
	ConfigPath string
	Port       int
	DataDir    string
	Mode       string
	Version    string
}

// Run 启动采集端并阻塞，直到 ctx 取消。
func Run(ctx context.Context, opts Options) error {
	store, err := config.Load(opts.ConfigPath)
	if err != nil {
		return err
	}
	if err := applyOverrides(store, opts); err != nil {
		return err
	}
	cfg := store.Get()

	log := logx.New(1000, slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})))
	st := state.New(500)
	st.SetMode(cfg.Agent.Mode)

	log.Infof("labgate %s 启动中（配置 %s）", opts.Version, store.Path())

	b, err := bus.Start(ctx, cfg, log)
	if err != nil {
		return err
	}
	defer b.Close()

	setupCtx, cancelSetup := context.WithTimeout(ctx, 30*time.Second)
	stream, err := b.EnsureLocalStream(setupCtx)
	cancelSetup()
	if err != nil {
		return err
	}
	if info, err := stream.Info(ctx); err == nil {
		log.Infof("本地读数流 %s 就绪：已缓冲 %d 条 / %.1f MB",
			info.Config.Name, info.State.Msgs, float64(info.State.Bytes)/(1024*1024))
	}

	ing := ingest.New(b.LocalJS(), store.Get, st, log)

	acquireCtx, stopAcquire := context.WithCancel(ctx)
	defer stopAcquire()
	mgr := acquire.NewManager(acquireCtx, store.Get,
		func(ctx context.Context, code, raw, value, unit string, push bool) {
			if _, err := ing.Submit(ctx, code, raw, value, unit, push); err != nil {
				// 具体原因已在 ingest 内按仪器去重记录，这里不重复刷日志
				_ = err
			}
		}, log)

	poller := limspoll.New(store.Get, mgr, st, log)
	cloud := forward.NewCloud(b, store.Get, st, log)
	lims := forward.NewLIMS(b, store.Get, st, log)

	var wg sync.WaitGroup
	run := func(name string, fn func(context.Context) error) {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := fn(ctx); err != nil && ctx.Err() == nil {
				log.Errorf("%s 异常退出：%v", name, err)
			}
		}()
	}
	run("云端转发", cloud.Run)
	run("HTTP 直推", lims.Run)
	run("云 LIMS 轮询", poller.Run)

	startLocalInstruments(store.Get(), mgr, log)

	srv, err := httpapi.New(httpapi.Deps{
		Config:  store,
		State:   st,
		Log:     log,
		Acquire: mgr,
		Ingest:  ing,
		Bus:     b,
		Poller:  poller,
		Version: opts.Version,
	})
	if err != nil {
		return err
	}

	addr := net.JoinHostPort(cfg.Agent.Host, strconv.Itoa(cfg.Agent.Port))
	httpServer := &http.Server{
		Handler:           srv.Handler(),
		ReadHeaderTimeout: 10 * time.Second,
	}
	listener, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("监听 %s 失败: %w", addr, err)
	}

	log.Infof("管理界面已启动：http://%s", displayAddr(cfg.Agent.Host, cfg.Agent.Port))
	fmt.Printf("\n  labgate %s 已启动\n  管理界面  http://%s\n  数据目录  %s\n\n",
		opts.Version, displayAddr(cfg.Agent.Host, cfg.Agent.Port), cfg.JetStreamDir())

	serveErr := make(chan error, 1)
	go func() {
		if err := httpServer.Serve(listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			serveErr <- err
		}
		close(serveErr)
	}()

	select {
	case <-ctx.Done():
	case err := <-serveErr:
		if err != nil {
			return err
		}
	}

	log.Infof("正在关闭……")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpServer.Shutdown(shutdownCtx)
	stopAcquire()
	mgr.Close()
	wg.Wait()
	log.Infof("已退出")
	return nil
}

// applyOverrides 把命令行参数写回配置（多实例部署时各自指定端口与数据目录）。
func applyOverrides(store *config.Store, opts Options) error {
	patch := map[string]any{}
	agent := map[string]any{}
	if opts.Port > 0 {
		agent["port"] = opts.Port
	}
	if opts.Mode != "" {
		if opts.Mode != "auto" && opts.Mode != "manual" {
			return fmt.Errorf("--mode 只能是 auto 或 manual，收到 %q", opts.Mode)
		}
		agent["mode"] = opts.Mode
	}
	if len(agent) > 0 {
		patch["agent"] = agent
	}
	if opts.DataDir != "" {
		patch["cache"] = map[string]any{"dir": opts.DataDir}
	}
	if len(patch) == 0 {
		return nil
	}
	_, err := store.Update(patch)
	return err
}

// startLocalInstruments 启动本地配置里的仪器。
//
// 由云 LIMS 下发仪器清单时（自动模式 + 开启轮询）不在这里启动，
// 交给轮询器按 LIMS 的启停指令来控制。
func startLocalInstruments(cfg config.Config, mgr *acquire.Manager, log *logx.Logger) {
	if cfg.Agent.Mode == "auto" && cfg.Cloud.PollEnabled {
		log.Infof("自动模式：仪器的启停由云 LIMS 下发")
		return
	}
	instruments := cfg.EnabledInstruments()
	if len(instruments) == 0 {
		log.Infof("本地未配置仪器，可在「采集」页手动开始，或在 config.json 的 instruments 里登记")
		return
	}
	for _, inst := range instruments {
		mgr.Start(inst.Code, inst.Host, inst.Port, inst.ShouldPush())
	}
	log.Infof("已按本地配置启动 %d 台仪器的采集", len(instruments))
}

func displayAddr(host string, port int) string {
	if host == "" || host == "0.0.0.0" || host == "::" {
		host = "127.0.0.1"
	}
	return net.JoinHostPort(host, strconv.Itoa(port))
}
