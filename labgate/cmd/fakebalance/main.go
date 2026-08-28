// fakebalance 是一台模拟天平：监听 TCP，按固定间隔发出读数。
//
// 用于在没有真实仪器时联调整条链路（采集 → 落盘 → 上云）。
//
//	fakebalance --listen 0.0.0.0:9000 --interval 2s
package main

import (
	"flag"
	"fmt"
	"log"
	"math/rand/v2"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	var (
		listen   = flag.String("listen", "0.0.0.0:9000", "监听地址")
		interval = flag.Duration("interval", 2*time.Second, "发送间隔")
		unit     = flag.String("unit", "mg", "单位")
		format   = flag.String("format", "ST,GS,%s,%s", "输出格式（值、单位）")
		noEOL    = flag.Bool("no-eol", false, "不发换行符（模拟部分串口服务器）")
	)
	flag.Parse()

	ln, err := net.Listen("tcp", *listen)
	if err != nil {
		log.Fatalf("监听 %s 失败: %v", *listen, err)
	}
	defer ln.Close()
	log.Printf("模拟天平已启动，监听 %s，每 %s 发一条读数", *listen, *interval)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	go func() {
		<-stop
		log.Println("正在退出")
		ln.Close()
	}()

	for {
		conn, err := ln.Accept()
		if err != nil {
			return
		}
		go serve(conn, *interval, *unit, *format, *noEOL)
	}
}

func serve(conn net.Conn, interval time.Duration, unit, format string, noEOL bool) {
	defer conn.Close()
	log.Printf("采集端已连接：%s", conn.RemoteAddr())

	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for range ticker.C {
		// 在 0.9000 上下小幅波动，像一台正在称量的天平
		value := fmt.Sprintf("%.4f", 0.9+rand.Float64()*0.1)
		line := fmt.Sprintf(format, value, unit)
		if !noEOL {
			line += "\r\n"
		}
		if _, err := conn.Write([]byte(line)); err != nil {
			log.Printf("采集端已断开：%s", conn.RemoteAddr())
			return
		}
	}
}
