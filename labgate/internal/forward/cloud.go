// Package forward 把本地 JetStream 中的读数转发出去。
//
// 有两条独立的出口，各自持有自己的 durable consumer，互不影响：
//   - cloud.go：经 NATS LeafNode 发到云端 JetStream（主链路）
//   - lims.go：HTTP 直推 SENAITE ingest 接口（可选，默认关闭）
//
// 两者都是「取一条 → 送达确认 → ack」；送不出去就 nak 重投，
// 消息留在本地 JetStream 里，断网期间不会丢，恢复后自动续传。
package forward

import (
	"context"
	"errors"
	"time"

	"github.com/maitux/labgate/internal/bus"
	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/logx"
	"github.com/maitux/labgate/internal/model"
	"github.com/maitux/labgate/internal/state"
	"github.com/nats-io/nats.go/jetstream"
)

// CloudConsumer 是云端转发器使用的 durable consumer 名。
const CloudConsumer = "cloud-forward"

// Cloud 把本地读数转发到云端 JetStream。
type Cloud struct {
	b   *bus.Bus
	cfg func() config.Config
	st  *state.State
	log *logx.Logger
}

// NewCloud 构造云端转发器。
func NewCloud(b *bus.Bus, cfg func() config.Config, st *state.State, log *logx.Logger) *Cloud {
	return &Cloud{b: b, cfg: cfg, st: st, log: log}
}

// Run 启动转发，阻塞直到 ctx 取消。
func (c *Cloud) Run(ctx context.Context) error {
	cfg := c.cfg()
	if !cfg.NATS.Leaf.Enabled {
		c.log.Infof("云端转发未启用（nats.leaf.enabled=false），读数仅在本地 JetStream 留存")
		<-ctx.Done()
		return nil
	}

	stream, err := c.b.LocalJS().Stream(ctx, streamName(cfg))
	if err != nil {
		return err
	}

	consumer, err := stream.CreateOrUpdateConsumer(ctx, jetstream.ConsumerConfig{
		Durable:       CloudConsumer,
		Description:   "转发到云端 NATS 的进度游标",
		AckPolicy:     jetstream.AckExplicitPolicy,
		DeliverPolicy: jetstream.DeliverAllPolicy,
		FilterSubject: cfg.LocalSubjectFilter(),
		AckWait:       60 * time.Second,
		// 不设投递次数上限：网络中断可能持续数小时，
		// 数据保留由流的 max_age / max_bytes 决定，而不是投递次数。
		MaxDeliver:    -1,
		MaxAckPending: 256,
	})
	if err != nil {
		return err
	}

	if cfg.NATS.Leaf.EnsureHubStream {
		go c.ensureHubStream(ctx)
	}

	cc, err := consumer.Consume(c.handle)
	if err != nil {
		return err
	}
	defer cc.Stop()

	c.log.Infof("云端转发已启动：%s → %s.%s.readings.*（云端流 %s）",
		cfg.LocalSubjectFilter(), cfg.NATS.Leaf.HubSubjectPrefix,
		config.SanitizeToken(cfg.Agent.SiteID), cfg.NATS.Leaf.HubStream)

	// 定期把待转发条数与 LeafNode 连通状态同步给界面
	ticker := time.NewTicker(3 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			c.st.SetLeafConnected(c.b.LeafConnected())
			if info, err := consumer.Info(ctx); err == nil {
				c.st.SetPending(int64(info.NumPending) + int64(info.NumAckPending))
			}
		}
	}
}

// ensureHubStream 在 LeafNode 连上之后创建云端读数流。
func (c *Cloud) ensureHubStream(ctx context.Context) {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for {
		if c.b.LeafConnected() {
			ctxT, cancel := context.WithTimeout(ctx, 10*time.Second)
			err := c.b.EnsureHubStream(ctxT)
			cancel()
			if err == nil {
				c.log.Infof("云端读数流已就绪：%s", c.cfg().NATS.Leaf.HubStream)
				return
			}
			c.log.Dedupf("hubstream", logx.LevelWarning, "创建云端读数流失败：%v", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

// handle 处理一条待转发读数。
func (c *Cloud) handle(msg jetstream.Msg) {
	cfg := c.cfg()
	reading, err := model.DecodeReading(msg.Data())
	if err != nil {
		// 无法解析的消息重投多少次都不会成功，直接终止投递避免死循环
		c.log.Errorf("跳过一条无法解析的本地消息（%s）：%v", msg.Subject(), err)
		_ = msg.Term()
		return
	}

	hub := c.b.HubJS()
	if hub == nil || !c.b.LeafConnected() {
		c.retry(msg, errors.New("云端未连接"))
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(),
		time.Duration(config.OrDefaultInt(cfg.NATS.Leaf.AckTimeoutSeconds, 10))*time.Second)
	defer cancel()

	_, err = hub.Publish(ctx, cfg.HubSubject(reading.InstrumentCode), msg.Data(),
		jetstream.WithMsgID(reading.EventID),
		jetstream.WithExpectStream(cfg.NATS.Leaf.HubStream),
		// 本地已经有重投机制，publish 本身不再自旋重试
		jetstream.WithRetryAttempts(0),
	)
	if err != nil {
		c.retry(msg, err)
		return
	}

	if err := msg.Ack(); err != nil {
		c.log.Warnf("确认本地消息失败（%s）：%v", reading.EventID, err)
		return
	}
	c.st.IncPushOK()
	c.st.MarkForwarded()
	c.st.SetLeaf(true, "")
	c.log.ResetDedup("forward")
}

// retry 让消息稍后重投，并把失败原因反映到界面。
func (c *Cloud) retry(msg jetstream.Msg, cause error) {
	cfg := c.cfg()
	c.st.IncPushFail()
	c.st.SetLeaf(c.b.LeafConnected(), cause.Error())

	delay := time.Duration(config.OrDefaultInt(cfg.NATS.Leaf.RetryDelaySeconds, 5)) * time.Second
	// 反复失败（多为长时间断网）后拉长退避，别把 CPU 和日志耗在空转上
	if meta, err := msg.Metadata(); err == nil {
		if maxRetries := config.OrDefaultInt(cfg.Cache.MaxRetries, 5); int(meta.NumDelivered) > maxRetries {
			delay *= 6
			if delay > time.Minute {
				delay = time.Minute
			}
		}
	}
	c.log.Dedupf("forward", logx.LevelWarning,
		"转发到云端失败，%s 后重试：%v（数据已在本地留存，不会丢）", delay, cause)
	_ = msg.NakWithDelay(delay)
}

func streamName(cfg config.Config) string {
	if cfg.NATS.Stream == "" {
		return "READINGS"
	}
	return cfg.NATS.Stream
}
