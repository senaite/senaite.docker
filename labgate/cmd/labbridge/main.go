// labbridge 在云端把 NATS 里的读数投递给 SENAITE。
//
//	各实验室 labgate ──LeafNode──► 云端 NATS ──► labbridge ──HTTP──► SENAITE
//
// 它跟着 LIMS 的采集会话走：仪器有「监听中的会话」才投递，并从会话开始前
// 一段时间起投（技术员先称量、后点开始采集，那几分钟也能归进去）；没有会话
// 的读数留在 JetStream 里，既不灌进 LIMS，也不丢。
//
// 用法：
//
//	labbridge                          # 用当前目录的 bridge.json
//	labbridge --config /etc/bridge.json
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/maitux/labgate/internal/bridge"
)

// version 由构建时通过 -ldflags "-X main.version=..." 注入。
var version = "dev"

func main() {
	var (
		configPath  = flag.String("config", "bridge.json", "配置文件路径")
		showVersion = flag.Bool("version", false, "打印版本号后退出")
	)
	flag.Parse()

	if *showVersion {
		fmt.Println("labbridge", version)
		return
	}

	cfg, err := bridge.LoadConfig(*configPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "错误：", err)
		os.Exit(1)
	}

	ctx, stop := signal.NotifyContext(context.Background(),
		os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := bridge.Run(ctx, cfg, version); err != nil && !errors.Is(err, context.Canceled) {
		fmt.Fprintln(os.Stderr, "错误：", err)
		os.Exit(1)
	}
}
