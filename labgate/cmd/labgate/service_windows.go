//go:build windows

package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/mgr"
)

const (
	serviceName        = "labgate"
	serviceDisplayName = "labgate 仪器采集网关"
	serviceDescription = "连接实验室仪器，采集读数并同步到云端 LIMS。"
)

// runAsService 在进程由服务控制管理器拉起时接管运行；
// 命令行直接运行时返回 false，走普通流程。
func runAsService(run func(context.Context) error) (bool, error) {
	isService, err := svc.IsWindowsService()
	if err != nil || !isService {
		return false, nil //nolint:nilerr // 判断不出来就按普通进程跑
	}
	return true, svc.Run(serviceName, &serviceHandler{run: run})
}

type serviceHandler struct {
	run func(context.Context) error
}

// Execute 是服务控制管理器的回调：把 Stop/Shutdown 转成 ctx 取消。
func (h *serviceHandler) Execute(_ []string,
	requests <-chan svc.ChangeRequest, status chan<- svc.Status) (bool, uint32) {

	const accepted = svc.AcceptStop | svc.AcceptShutdown
	status <- svc.Status{State: svc.StartPending}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	done := make(chan error, 1)
	go func() { done <- h.run(ctx) }()

	status <- svc.Status{State: svc.Running, Accepts: accepted}
	for {
		select {
		case req := <-requests:
			switch req.Cmd {
			case svc.Interrogate:
				status <- req.CurrentStatus
			case svc.Stop, svc.Shutdown:
				status <- svc.Status{State: svc.StopPending}
				cancel()
				select {
				case <-done:
				case <-time.After(20 * time.Second):
				}
				status <- svc.Status{State: svc.Stopped}
				return false, 0
			}
		case err := <-done:
			status <- svc.Status{State: svc.Stopped}
			if err != nil {
				return false, 1
			}
			return false, 0
		}
	}
}

// installService 注册开机自启的 Windows 服务。
//
// 服务进程的工作目录是 system32，所以这里把配置与数据目录都换算成
// 绝对路径写进服务参数，避免相对路径找不到文件。
func installService(configPath, dataDir string, port int) error {
	exe, err := os.Executable()
	if err != nil {
		return fmt.Errorf("取当前程序路径失败: %w", err)
	}
	exeDir := filepath.Dir(exe)

	if configPath == "" {
		configPath = "config.json"
	}
	if !filepath.IsAbs(configPath) {
		configPath = filepath.Join(exeDir, configPath)
	}
	args := []string{"--config", configPath}
	if dataDir != "" {
		if !filepath.IsAbs(dataDir) {
			dataDir = filepath.Join(exeDir, dataDir)
		}
		args = append(args, "--data-dir", dataDir)
	} else {
		args = append(args, "--data-dir", filepath.Join(exeDir, "data"))
	}
	if port > 0 {
		args = append(args, "--port", fmt.Sprint(port))
	}

	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("连接服务管理器失败（需要以管理员身份运行）: %w", err)
	}
	defer m.Disconnect()

	if s, err := m.OpenService(serviceName); err == nil {
		s.Close()
		return fmt.Errorf("服务 %s 已存在，请先执行 --uninstall-service", serviceName)
	}

	s, err := m.CreateService(serviceName, exe, mgr.Config{
		DisplayName:  serviceDisplayName,
		Description:  serviceDescription,
		StartType:    mgr.StartAutomatic,
		ErrorControl: mgr.ErrorNormal,
	}, args...)
	if err != nil {
		return fmt.Errorf("创建服务失败: %w", err)
	}
	defer s.Close()

	// 崩溃后自动重启：10 秒后重试，最多连续三次，一天后重置计数
	if err := s.SetRecoveryActions([]mgr.RecoveryAction{
		{Type: mgr.ServiceRestart, Delay: 10 * time.Second},
		{Type: mgr.ServiceRestart, Delay: 30 * time.Second},
		{Type: mgr.ServiceRestart, Delay: 60 * time.Second},
	}, uint32((24 * time.Hour).Seconds())); err != nil {
		fmt.Fprintln(os.Stderr, "提示：设置自动重启策略失败：", err)
	}

	if err := s.Start(); err != nil {
		return fmt.Errorf("服务已创建但启动失败: %w", err)
	}
	fmt.Printf("服务 %s 已安装并启动\n  程序   %s\n  参数   %v\n",
		serviceName, exe, args)
	return nil
}

// uninstallService 停止并删除服务。
func uninstallService() error {
	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("连接服务管理器失败（需要以管理员身份运行）: %w", err)
	}
	defer m.Disconnect()

	s, err := m.OpenService(serviceName)
	if err != nil {
		return fmt.Errorf("服务 %s 不存在", serviceName)
	}
	defer s.Close()

	if st, err := s.Control(svc.Stop); err == nil {
		deadline := time.Now().Add(20 * time.Second)
		for st.State != svc.Stopped && time.Now().Before(deadline) {
			time.Sleep(300 * time.Millisecond)
			if st, err = s.Query(); err != nil {
				break
			}
		}
	}
	if err := s.Delete(); err != nil {
		return fmt.Errorf("删除服务失败: %w", err)
	}
	fmt.Printf("服务 %s 已卸载\n", serviceName)
	return nil
}
