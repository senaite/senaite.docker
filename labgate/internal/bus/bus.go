// Package bus 启动内嵌的 NATS 服务器，并提供 JetStream 客户端。
//
// 采集端自身就是一个 NATS LeafNode：
//
//	仪器 ──► labgate（内嵌 NATS，JetStream 落盘）──LeafNode──► 云端 NATS
//
// 这样「断网不丢数据、恢复后自动续传」由 NATS/JetStream 这一成熟中间件保证，
// 而不是由采集端自己实现重试队列。
//
// 默认不监听任何 TCP 端口（DontListen），采集端以进程内方式连接自己的
// NATS，Windows 下不会触发防火墙弹窗；需要用 nats CLI 观察时可在配置里
// 打开 nats.listen。
package bus

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"net"
	"net/url"
	"os"
	"strconv"
	"time"

	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/logx"
	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

// Bus 持有内嵌 NATS 服务器与其客户端连接。
type Bus struct {
	ns  *server.Server
	nc  *nats.Conn
	js  jetstream.JetStream // 边缘侧（本地 domain）
	hub jetstream.JetStream // 云端 domain（LeafNode 未启用时为 nil）

	cfg config.Config
	log *logx.Logger
}

// Start 启动内嵌 NATS 服务器并建立进程内客户端连接。
func Start(ctx context.Context, cfg config.Config, log *logx.Logger) (*Bus, error) {
	storeDir := cfg.JetStreamDir()
	if err := os.MkdirAll(storeDir, 0o755); err != nil {
		return nil, fmt.Errorf("创建 JetStream 存储目录 %s 失败: %w", storeDir, err)
	}

	opts, err := buildOptions(cfg, storeDir)
	if err != nil {
		return nil, err
	}

	ns, err := server.NewServer(opts)
	if err != nil {
		return nil, fmt.Errorf("初始化内嵌 NATS 失败: %w", err)
	}
	ns.SetLogger(&natsLogger{log: log}, false, false)
	go ns.Start()

	if !ns.ReadyForConnections(15 * time.Second) {
		ns.Shutdown()
		return nil, errors.New("内嵌 NATS 启动超时")
	}

	nc, err := connect(ns, cfg)
	if err != nil {
		ns.Shutdown()
		return nil, err
	}

	js, err := jetstream.New(nc)
	if err != nil {
		nc.Close()
		ns.Shutdown()
		return nil, fmt.Errorf("初始化本地 JetStream 失败: %w", err)
	}

	b := &Bus{ns: ns, nc: nc, js: js, cfg: cfg, log: log}

	if cfg.NATS.Leaf.Enabled {
		hubDomain := cfg.NATS.Leaf.HubDomain
		if hubDomain == "" {
			hubDomain = "hub"
		}
		hub, err := jetstream.NewWithDomain(nc, hubDomain)
		if err != nil {
			log.Warnf("初始化云端 JetStream 客户端失败（domain=%s）：%v", hubDomain, err)
		} else {
			b.hub = hub
		}
	}

	if cfg.NATS.Listen != "" {
		log.Infof("内嵌 NATS 已启动，监听 %s（JetStream domain=%s，存储 %s）",
			cfg.NATS.Listen, opts.JetStreamDomain, storeDir)
	} else {
		log.Infof("内嵌 NATS 已启动（进程内模式，未监听端口；JetStream domain=%s，存储 %s）",
			opts.JetStreamDomain, storeDir)
	}
	if cfg.NATS.Leaf.Enabled {
		log.Infof("LeafNode 已配置，云端地址 %s", cfg.NATS.Leaf.SafeURL())
	} else {
		log.Infof("LeafNode 未启用：读数只在本地 JetStream 落盘，配置 nats.leaf 后自动上云")
	}
	return b, nil
}

func buildOptions(cfg config.Config, storeDir string) (*server.Options, error) {
	name := cfg.NATS.ServerName
	if name == "" {
		name = "labgate"
	}
	domain := cfg.NATS.Domain
	if domain == "" {
		domain = "edge"
	}

	opts := &server.Options{
		ServerName:      name,
		JetStream:       true,
		JetStreamDomain: domain,
		StoreDir:        storeDir,
		NoSigs:          true,
		NoLog:           false,
		DontListen:      true,
	}

	if addr := cfg.NATS.Listen; addr != "" {
		host, port, err := splitHostPort(addr, 4222)
		if err != nil {
			return nil, fmt.Errorf("nats.listen 无效（%s）: %w", addr, err)
		}
		opts.DontListen = false
		opts.Host = host
		opts.Port = port
	}

	if addr := cfg.NATS.MonitorListen; addr != "" {
		host, port, err := splitHostPort(addr, 8222)
		if err != nil {
			return nil, fmt.Errorf("nats.monitor_listen 无效（%s）: %w", addr, err)
		}
		opts.HTTPHost = host
		opts.HTTPPort = port
	}

	leaf := cfg.NATS.Leaf
	if leaf.Enabled {
		if leaf.URL == "" {
			return nil, errors.New("已启用 nats.leaf 但未填 nats.leaf.url")
		}
		u, err := url.Parse(leaf.URL)
		if err != nil {
			return nil, fmt.Errorf("nats.leaf.url 无效（%s）: %w", leaf.URL, err)
		}
		// 账号密码写进 URL 的 userinfo —— LeafNode remote 的认证方式
		if leaf.Credentials == "" && leaf.User != "" {
			u.User = url.UserPassword(leaf.User, leaf.Password)
		}
		remote := &server.RemoteLeafOpts{URLs: []*url.URL{u}}
		if leaf.Credentials != "" {
			remote.Credentials = leaf.Credentials
		}
		if leaf.TLSInsecure {
			remote.TLSConfig = &tls.Config{InsecureSkipVerify: true} //nolint:gosec // 自签证书内网部署时按需打开
		}
		opts.LeafNode.Remotes = []*server.RemoteLeafOpts{remote}
	}
	return opts, nil
}

func connect(ns *server.Server, cfg config.Config) (*nats.Conn, error) {
	name := cfg.NATS.ServerName
	if name == "" {
		name = "labgate"
	}
	opts := []nats.Option{
		nats.Name(name + "-agent"),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(time.Second),
		// 进程内连接：不经过 TCP，也不受 DontListen 影响
		nats.InProcessServer(ns),
	}
	nc, err := nats.Connect("", opts...)
	if err != nil {
		return nil, fmt.Errorf("连接内嵌 NATS 失败: %w", err)
	}
	return nc, nil
}

func splitHostPort(addr string, defPort int) (string, int, error) {
	host, portStr, err := net.SplitHostPort(addr)
	if err != nil {
		// 只写了端口号或只写了主机名
		if p, convErr := strconv.Atoi(addr); convErr == nil {
			return "0.0.0.0", p, nil
		}
		return addr, defPort, nil //nolint:nilerr // 只给了主机名时用默认端口
	}
	port, err := strconv.Atoi(portStr)
	if err != nil {
		return "", 0, err
	}
	if host == "" {
		host = "0.0.0.0"
	}
	return host, port, nil
}

// Conn 返回进程内 NATS 客户端连接。
func (b *Bus) Conn() *nats.Conn { return b.nc }

// LocalJS 返回边缘侧 JetStream 客户端。
func (b *Bus) LocalJS() jetstream.JetStream { return b.js }

// HubJS 返回云端 JetStream 客户端；LeafNode 未启用时为 nil。
func (b *Bus) HubJS() jetstream.JetStream { return b.hub }

// LeafConnected 返回 LeafNode 是否已连上云端。
func (b *Bus) LeafConnected() bool {
	if b.ns == nil || !b.cfg.NATS.Leaf.Enabled {
		return false
	}
	return b.ns.NumLeafNodes() > 0
}

// Close 关闭客户端连接与内嵌服务器。
func (b *Bus) Close() {
	if b.nc != nil {
		// Drain 会先把未发出的消息发完再关闭
		_ = b.nc.Drain()
		deadline := time.Now().Add(3 * time.Second)
		for b.nc.IsDraining() && time.Now().Before(deadline) {
			time.Sleep(20 * time.Millisecond)
		}
		b.nc.Close()
	}
	if b.ns != nil {
		b.ns.Shutdown()
		b.ns.WaitForShutdown()
	}
}

// natsLogger 把 NATS 服务器日志转接到采集端日志（供界面「日志」页查看）。
type natsLogger struct{ log *logx.Logger }

func (l *natsLogger) Noticef(format string, v ...any) { l.log.Infof("[nats] "+format, v...) }
func (l *natsLogger) Warnf(format string, v ...any)   { l.log.Warnf("[nats] "+format, v...) }
func (l *natsLogger) Fatalf(format string, v ...any)  { l.log.Errorf("[nats] "+format, v...) }
func (l *natsLogger) Errorf(format string, v ...any)  { l.log.Errorf("[nats] "+format, v...) }
func (l *natsLogger) Debugf(format string, v ...any)  {}
func (l *natsLogger) Tracef(format string, v ...any)  {}
