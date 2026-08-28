// labgate 是实验室仪器数据采集网关（边缘节点）。
//
// 它连接本地仪器的 TCP 通道，解析读数，写入内嵌 NATS 的 JetStream 落盘，
// 再通过 NATS LeafNode 同步到云端；断网期间数据留在本地，恢复后自动续传。
//
// 用法：
//
//	labgate                                   # 用当前目录的 config.json
//	labgate --port 8091 --config b.json --data-dir data2
//	labgate --mode manual                     # 覆盖运行模式
//	labgate --install-service                 # 注册为 Windows 服务（需管理员）
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/maitux/labgate/internal/app"
)

// version 由构建时通过 -ldflags "-X main.version=..." 注入。
var version = "dev"

func main() {
	var (
		configPath = flag.String("config", "config.json", "配置文件路径（多实例时各自指定）")
		port       = flag.Int("port", 0, "管理界面端口（覆盖配置文件）")
		dataDir    = flag.String("data-dir", "", "数据目录（多实例时各自独立）")
		mode       = flag.String("mode", "", "运行模式：auto 或 manual（覆盖配置文件）")

		showVersion = flag.Bool("version", false, "打印版本号后退出")
		install     = flag.Bool("install-service", false,
			"注册为 Windows 服务并启动（需要管理员权限）")
		uninstall = flag.Bool("uninstall-service", false,
			"停止并删除 Windows 服务（需要管理员权限）")
	)
	flag.Parse()

	switch {
	case *showVersion:
		fmt.Println("labgate", version)
		return
	case *install:
		exit(installService(*configPath, *dataDir, *port))
		return
	case *uninstall:
		exit(uninstallService())
		return
	}

	run := func(ctx context.Context) error {
		return app.Run(ctx, app.Options{
			ConfigPath: *configPath,
			Port:       *port,
			DataDir:    *dataDir,
			Mode:       *mode,
			Version:    version,
		})
	}

	// 由 Windows 服务控制管理器拉起时走服务流程（Stop 会转成 ctx 取消）
	if handled, err := runAsService(run); handled {
		exit(err)
		return
	}

	ctx, stop := signal.NotifyContext(context.Background(),
		os.Interrupt, syscall.SIGTERM)
	defer stop()
	exit(run(ctx))
}

func exit(err error) {
	if err != nil && !errors.Is(err, context.Canceled) {
		fmt.Fprintln(os.Stderr, "错误：", err)
		os.Exit(1)
	}
}
