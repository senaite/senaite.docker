package forward

import (
	"context"
	"strings"
	"time"

	"github.com/maitux/labgate/internal/bus"
	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/limsapi"
	"github.com/maitux/labgate/internal/logx"
	"github.com/maitux/labgate/internal/model"
	"github.com/maitux/labgate/internal/state"
	"github.com/nats-io/nats.go/jetstream"
)

// LIMSConsumer 是 HTTP 直推使用的 durable consumer 名。
const LIMSConsumer = "lims-http"

// LIMS 把本地读数用 HTTP 直推到 SENAITE 的 ingest 接口。
//
// 这是与旧采集端保持兼容的可选出口，默认关闭（cloud.lims_push_enabled）。
//
// 注意：正式部署的推荐路径是「读数走 NATS 上云、由云端的 labbridge 投递给
// SENAITE」。打开这个开关意味着每个实验室都要能 HTTP 访问到 SENAITE，
// 又把 LeafNode 省掉的那件事加了回来。它的定位是联调与应急兜底。
type LIMS struct {
	b   *bus.Bus
	cfg func() config.Config
	st  *state.State
	log *logx.Logger
}

// NewLIMS 构造 HTTP 直推转发器。
func NewLIMS(b *bus.Bus, cfg func() config.Config, st *state.State, log *logx.Logger) *LIMS {
	return &LIMS{b: b, cfg: cfg, st: st, log: log}
}

// Enabled 返回当前配置下是否应该启用 HTTP 直推。
func (l *LIMS) Enabled() bool {
	cfg := l.cfg()
	return cfg.Cloud.LIMSPushEnabled && strings.TrimSpace(cfg.Cloud.LIMSURL) != ""
}

// Run 监听配置开关：打开时消费并直推，关闭时停下来等待。
func (l *LIMS) Run(ctx context.Context) error {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for {
		if l.Enabled() {
			if err := l.consume(ctx); err != nil && ctx.Err() == nil {
				l.log.Warnf("HTTP 直推启动失败：%v（5 秒后重试）", err)
			}
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}

// consume 建立消费并一直运行，直到配置关闭或 ctx 取消。
func (l *LIMS) consume(ctx context.Context) error {
	cfg := l.cfg()
	stream, err := l.b.LocalJS().Stream(ctx, streamName(cfg))
	if err != nil {
		return err
	}
	consumer, err := stream.CreateOrUpdateConsumer(ctx, jetstream.ConsumerConfig{
		Durable:       LIMSConsumer,
		Description:   "HTTP 直推 SENAITE 的进度游标",
		AckPolicy:     jetstream.AckExplicitPolicy,
		DeliverPolicy: jetstream.DeliverAllPolicy,
		FilterSubject: cfg.LocalSubjectFilter(),
		AckWait:       60 * time.Second,
		MaxDeliver:    -1,
		MaxAckPending: 64,
	})
	if err != nil {
		return err
	}
	cc, err := consumer.Consume(l.handle(ctx))
	if err != nil {
		return err
	}
	defer cc.Stop()
	l.log.Infof("HTTP 直推已启动：%s",
		strings.TrimRight(cfg.Cloud.LIMSURL, "/")+limsapi.IngestPath)

	ticker := time.NewTicker(3 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			if !l.Enabled() {
				l.log.Infof("HTTP 直推已按配置停止")
				return nil
			}
		}
	}
}

func (l *LIMS) handle(ctx context.Context) jetstream.MessageHandler {
	return func(msg jetstream.Msg) {
		cfg := l.cfg()
		reading, err := model.DecodeReading(msg.Data())
		if err != nil {
			_ = msg.Term()
			return
		}

		client := limsapi.New(cfg.Cloud.LIMSURL, cfg.Cloud.Token, cfg.PushTimeout())
		res := client.Ingest(ctx, msg.Data())

		switch res.Outcome {
		case limsapi.Accepted:
			_ = msg.Ack()
			l.log.ResetDedup("lims")

		case limsapi.NoSession, limsapi.Rejected:
			// LIMS 明确拒绝（多为该仪器当前没有在采集的会话）：
			// 重投到 cache.max_retries 次后放弃，与旧采集端行为一致。
			// 想要"等会话开了再补投"，用云端的 labbridge，那边是跟着会话走的。
			l.dropOrRetry(msg, cfg, reading, res.Message)

		default:
			delay := retryDelay(cfg)
			l.log.Dedupf("lims", logx.LevelWarning,
				"HTTP 直推失败，%s 后重试：%s", delay, res.Message)
			_ = msg.NakWithDelay(delay)
		}
	}
}

// dropOrRetry 在重投次数达到 cache.max_retries 后放弃该条（记日志）。
func (l *LIMS) dropOrRetry(msg jetstream.Msg, cfg config.Config, reading model.Reading, reason string) {
	maxRetries := config.OrDefaultInt(cfg.Cache.MaxRetries, 5)
	delivered := 1
	if meta, err := msg.Metadata(); err == nil {
		delivered = int(meta.NumDelivered)
	}
	if delivered >= maxRetries {
		l.log.Warnf("HTTP 直推超限已放弃 %s（%s）：%s",
			reading.EventID, reading.RawText, reason)
		_ = msg.Term()
		return
	}
	delay := retryDelay(cfg)
	l.log.Dedupf("lims", logx.LevelWarning,
		"HTTP 直推被拒绝(%d/%d)，%s 后重试：%s", delivered, maxRetries, delay, reason)
	_ = msg.NakWithDelay(delay)
}

func retryDelay(cfg config.Config) time.Duration {
	return time.Duration(config.OrDefaultInt(cfg.Cache.RetryDelaySeconds, 5)) * time.Second
}
