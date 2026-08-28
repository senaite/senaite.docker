// Package ingest 把采集到的读数写入本地 JetStream。
//
// 这是"落盘不丢"的关键一步：TCP 收到一行 → 立即同步写入 JetStream 文件存储
// → 拿到 PubAck 才算收下。之后是否能上云由转发器负责，与采集解耦。
package ingest

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"time"

	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/logx"
	"github.com/maitux/labgate/internal/model"
	"github.com/maitux/labgate/internal/state"
	"github.com/nats-io/nats.go/jetstream"
)

// 界面「实时数据」表的状态列取值。
const (
	StatusBuffered  = "已落盘"
	StatusLocalOnly = "仅本地"
	StatusFailed    = "落盘失败"
)

// Ingestor 负责组装读数事件并写入本地 JetStream。
type Ingestor struct {
	js  jetstream.JetStream
	cfg func() config.Config
	st  *state.State
	log *logx.Logger
}

// New 构造 Ingestor。
func New(js jetstream.JetStream, cfg func() config.Config, st *state.State, log *logx.Logger) *Ingestor {
	return &Ingestor{js: js, cfg: cfg, st: st, log: log}
}

// NewEventID 生成一个幂等键。
//
// 沿用旧采集端 "agent-<32位十六进制>" 的格式：云端 SENAITE 用它做去重，
// 换格式会让新旧数据的去重逻辑不一致。
func NewEventID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		// crypto/rand 失败时退化为时间戳，仍然保证本地唯一
		return fmt.Sprintf("agent-%016x%016x", time.Now().UnixNano(), time.Now().Unix())
	}
	return "agent-" + hex.EncodeToString(b[:])
}

// Submit 记录一条读数：写入界面缓冲，并在 push 为真时落盘到 JetStream。
//
// push 为假时只在界面显示、不上云（对应界面上的"推送到云"开关，
// 用于现场联调时观察仪器输出而不污染 LIMS 数据）。
func (i *Ingestor) Submit(ctx context.Context, code, raw, value, unit string, push bool) (model.Reading, error) {
	cfg := i.cfg()
	reading := model.NewReading(NewEventID(), cfg.Agent.SiteID, code, raw, value, unit)

	if !push || !cfg.Agent.PushEnabled {
		i.st.AddReading(code, raw, value, unit, StatusLocalOnly)
		i.st.IncPushSkipped()
		return reading, nil
	}

	data, err := reading.Encode()
	if err != nil {
		i.st.AddReading(code, raw, value, unit, StatusFailed)
		return reading, fmt.Errorf("序列化读数失败: %w", err)
	}

	pubCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	_, err = i.js.Publish(pubCtx, cfg.LocalSubject(code), data,
		jetstream.WithMsgID(reading.EventID))
	if err != nil {
		i.st.AddReading(code, raw, value, unit, StatusFailed)
		i.log.Dedupf("ingest:"+code, logx.LevelError,
			"[%s] 读数写入本地 JetStream 失败：%v", code, err)
		return reading, err
	}
	i.log.ResetDedup("ingest:" + code)
	i.st.AddReading(code, raw, value, unit, StatusBuffered)
	return reading, nil
}
