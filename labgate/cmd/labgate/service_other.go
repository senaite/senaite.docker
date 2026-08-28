//go:build !windows

package main

import (
	"context"
	"errors"
)

// runAsService 只在 Windows 上有意义；其他平台用 systemd 等系统自带的方式托管。
func runAsService(func(context.Context) error) (bool, error) { return false, nil }

func installService(string, string, int) error {
	return errors.New("--install-service 只支持 Windows；Linux 请用 deploy/labgate.service（systemd）")
}

func uninstallService() error {
	return errors.New("--uninstall-service 只支持 Windows")
}
