package bus

import (
	"context"
	"fmt"
	"time"

	"github.com/maitux/labgate/internal/config"
	"github.com/nats-io/nats.go/jetstream"
)

// EnsureLocalStream 创建或更新边缘侧读数流。
//
// 保留策略用 Limits + DiscardOld：读数被转发上云（ack）后仍然留在本地，
// 直到超过 max_age_hours / max_bytes_mb 才滚动淘汰。这样既能断网续传，
// 也能在本地回看一段时间的原始数据；磁盘占用有上限，不会无限增长。
func (b *Bus) EnsureLocalStream(ctx context.Context) (jetstream.Stream, error) {
	cfg := b.cfg
	name := cfg.NATS.Stream
	if name == "" {
		name = "READINGS"
	}
	scfg := jetstream.StreamConfig{
		Name:        name,
		Description: "labgate 边缘读数缓冲（断网续传）",
		Subjects:    []string{cfg.LocalSubjectFilter()},
		Storage:     jetstream.FileStorage,
		Retention:   jetstream.LimitsPolicy,
		Discard:     jetstream.DiscardOld,
		MaxAge:      time.Duration(config.OrDefaultInt(cfg.NATS.MaxAgeHours, 24*14)) * time.Hour,
		MaxBytes:    int64(config.OrDefaultInt(cfg.NATS.MaxBytesMB, 1024)) * 1024 * 1024,
		MaxMsgs:     -1,
		// 同一 event_id 在窗口内重复发布只保留一条（幂等）
		Duplicates: 5 * time.Minute,
		Replicas:   1,
	}
	if cfg.NATS.MaxMsgs > 0 {
		scfg.MaxMsgs = cfg.NATS.MaxMsgs
	}
	stream, err := b.js.CreateOrUpdateStream(ctx, scfg)
	if err != nil {
		return nil, fmt.Errorf("创建本地读数流 %s 失败: %w", name, err)
	}
	return stream, nil
}

// EnsureHubStream 在云端创建读数流。
//
// 仅当 nats.leaf.ensure_hub_stream 为 true 时调用：自建云端时省事；
// 云端由他人统一管理时应关闭，避免边缘节点改动云端配置。
func (b *Bus) EnsureHubStream(ctx context.Context) error {
	if b.hub == nil {
		return fmt.Errorf("云端 JetStream 客户端不可用（LeafNode 未连接）")
	}
	cfg := b.cfg
	name := cfg.NATS.Leaf.HubStream
	if name == "" {
		name = "LAB_READINGS"
	}
	_, err := b.hub.CreateOrUpdateStream(ctx, jetstream.StreamConfig{
		Name:        name,
		Description: "各实验室 labgate 上传的仪器读数",
		Subjects:    []string{cfg.HubSubjectFilter()},
		Storage:     jetstream.FileStorage,
		Retention:   jetstream.LimitsPolicy,
		Discard:     jetstream.DiscardOld,
		MaxAge:      90 * 24 * time.Hour,
		MaxMsgs:     -1,
		MaxBytes:    -1,
		Duplicates:  10 * time.Minute,
		Replicas:    1,
	})
	if err != nil {
		return fmt.Errorf("创建云端读数流 %s 失败: %w", name, err)
	}
	return nil
}
