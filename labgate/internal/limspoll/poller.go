// Package limspoll 在自动模式下轮询云 LIMS，按其指令启停各仪器的采集。
//
// 接口约定见 internal/limsapi。默认关闭（cloud.poll_enabled=false）：
// 第一阶段不与 SENAITE 对接，仪器由本地 instruments 配置或界面手动指定。
package limspoll

import (
	"context"
	"errors"
	"strings"
	"sync"
	"time"

	"github.com/maitux/labgate/internal/acquire"
	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/limsapi"
	"github.com/maitux/labgate/internal/logx"
	"github.com/maitux/labgate/internal/state"
)

// Poller 周期性拉取云端指令。
type Poller struct {
	cfg func() config.Config
	mgr *acquire.Manager
	st  *state.State
	log *logx.Logger

	mu sync.Mutex
	// lastCodes 是上一轮成功拉取到的仪器 code 集合。
	// 用于清理 LIMS 清单中已消失的仪器（删除模板/停用后残留连接）。
	lastCodes map[string]bool
}

// New 构造轮询器。
func New(cfg func() config.Config, mgr *acquire.Manager, st *state.State, log *logx.Logger) *Poller {
	return &Poller{cfg: cfg, mgr: mgr, st: st, log: log}
}

// Enabled 返回当前是否应该轮询云 LIMS。
func (p *Poller) Enabled() bool {
	cfg := p.cfg()
	return cfg.Agent.Mode == "auto" && cfg.Cloud.PollEnabled &&
		strings.TrimSpace(cfg.Cloud.LIMSURL) != ""
}

// Run 按配置的间隔轮询，阻塞直到 ctx 取消。
func (p *Poller) Run(ctx context.Context) error {
	logged := false
	for {
		if p.Enabled() {
			if !logged {
				p.log.Infof("云 LIMS 轮询已启动：%s（间隔 %s）",
					p.cfg().Cloud.LIMSURL, p.cfg().PollInterval())
				logged = true
			}
			if _, err := p.PullOnce(ctx); err != nil && ctx.Err() == nil {
				p.log.Dedupf("limspoll", logx.LevelWarning, "拉取云 LIMS 配置失败：%v", err)
			} else if err == nil {
				p.log.ResetDedup("limspoll")
			}
		} else {
			logged = false
		}
		select {
		case <-ctx.Done():
			return nil
		case <-time.After(p.cfg().PollInterval()):
		}
	}
}

// PullOnce 立即拉取一次并按结果启停采集（界面「立即拉取一次」也走这里）。
func (p *Poller) PullOnce(ctx context.Context) (map[string]any, error) {
	// 串行化：轮询循环与界面手动触发可能同时进来
	p.mu.Lock()
	defer p.mu.Unlock()

	cfg := p.cfg()
	client := limsapi.New(cfg.Cloud.LIMSURL, cfg.Cloud.Token, cfg.PushTimeout())
	if !client.Configured() {
		return nil, errors.New("未配置 cloud.lims_url")
	}

	instructions, err := client.Instruments(ctx)
	if err != nil {
		// 旧版 LIMS 没有 agent_instruments 接口：按本地仪器清单逐台拉 agent_config
		instructions, err = p.fallback(ctx, client, cfg)
		if err != nil {
			p.st.SetCloudPull(nil, err.Error())
			return nil, err
		}
	}

	result := make(map[string]any, len(instructions))
	current := make(map[string]bool, len(instructions))
	for _, ins := range instructions {
		if strings.TrimSpace(ins.Code) == "" {
			continue
		}
		current[ins.Code] = true
		result[ins.Code] = ins
		p.apply(ins)
	}

	// 清理：上轮在清单里、本轮消失的仪器，停止残留连接。
	// （LIMS 删除/停用模板后，若不处理，采集端会一直连着一台
	// 已经不存在于 LIMS 的仪器，读数也永远推不进。）
	for code := range p.lastCodes {
		if !current[code] && p.mgr.Running(code) {
			p.log.Infof("云同步：[%s] 已从 LIMS 仪器清单移除，停止采集", code)
			p.mgr.Stop(code)
		}
	}
	p.lastCodes = current

	p.st.SetCloudPull(result, "")
	return result, nil
}

// apply 按一条指令启动或停止该仪器的采集。
func (p *Poller) apply(ins limsapi.Instruction) {
	if ins.Start && ins.IP != "" && ins.Port > 0 {
		// Manager.Start 对同一目标是幂等的，这里不必自己判重
		p.mgr.Start(ins.Code, ins.IP, ins.Port, true)
		return
	}
	// 未在采集时每轮都调 Stop 会刷屏，Manager 内部只在确实有目标时记日志
	if p.mgr.Running(ins.Code) {
		if ins.Reason != "" {
			p.log.Infof("云同步：[%s] 停止采集（LIMS 原因：%s）", ins.Code, ins.Reason)
		}
		p.mgr.Stop(ins.Code)
	}
}

// fallback 逐台拉取旧的 agent_config 接口。
func (p *Poller) fallback(ctx context.Context, client *limsapi.Client,
	cfg config.Config) ([]limsapi.Instruction, error) {

	local := cfg.EnabledInstruments()
	if len(local) == 0 {
		return nil, errors.New("LIMS 无 agent_instruments 接口，且本地未配置仪器清单")
	}
	out := make([]limsapi.Instruction, 0, len(local))
	var lastErr error
	for _, inst := range local {
		ins, err := client.AgentConfig(ctx, inst.Code)
		if err != nil {
			lastErr = err
			continue
		}
		out = append(out, ins)
	}
	if len(out) == 0 && lastErr != nil {
		return nil, lastErr
	}
	return out, nil
}
