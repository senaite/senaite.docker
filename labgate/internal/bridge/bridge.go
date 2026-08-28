// Package bridge 在云端把 NATS 里的读数投递到 SENAITE。
//
//	各实验室 labgate ──LeafNode──► 云端 NATS  LAB_READINGS
//	                                              │
//	                                        labbridge（本包）
//	                                              │ HTTP
//	                                              ▼
//	                        @@instrument_acquisition_api_ingest
//
// 关键在于它是**跟着会话走**的，而不是收到就投、投不进就重试：
//
//   - 每台仪器一个 durable consumer，互不影响；某台仪器没有会话，
//     不会占住别人的投递额度。
//   - LIMS 里点了「开始采集」（agent_instruments 返回 start:true）才开始投递，
//     并且从「会话开始前 lookback」这个位置起投——技术员先称量、后点开始，
//     之前那几分钟的读数也能归进去。
//   - 会话关掉就停下来，消费位置留在原地；没有会话的读数原样躺在 JetStream 里，
//     既不会灌进 LIMS，也不会丢，到期由流的 max_age 自然淘汰。
package bridge

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"sync"
	"time"

	"github.com/maitux/labgate/internal/config"
	"github.com/maitux/labgate/internal/limsapi"
	"github.com/maitux/labgate/internal/logx"
	"github.com/maitux/labgate/internal/model"
	"github.com/nats-io/nats.go/jetstream"
)

// Options 是桥接层的运行参数。
type Options struct {
	Stream         string        // 云端读数流名，如 LAB_READINGS
	SubjectPrefix  string        // 云端主题前缀，如 lab
	ConsumerPrefix string        // durable consumer 名前缀
	Lookback       time.Duration // 会话开始前回溯多久
	PollInterval   time.Duration // 多久问一次 LIMS 哪些仪器在采集
	RetryDelay     time.Duration // 临时故障的重投间隔
	MaxAckPending  int
}

// InstrumentStatus 是一台仪器的投递情况（供 /api/status 展示）。
type InstrumentStatus struct {
	Code        string `json:"code"`
	Listening   bool   `json:"listening"`
	Delivering  bool   `json:"delivering"`
	Forwarded   int64  `json:"forwarded"`
	Skipped     int64  `json:"skipped"`
	Pending     uint64 `json:"pending"`
	LastError   string `json:"last_error"`
	LastForward string `json:"last_forward_at"`
}

// Bridge 按会话状态驱动各仪器的投递。
type Bridge struct {
	js   jetstream.JetStream
	lims *limsapi.Client
	opts Options
	log  *logx.Logger

	mu      sync.Mutex
	workers map[string]*worker
	// listening 记录上一轮观察到的会话状态，用来识别"会话刚开"这个跳变
	listening map[string]bool
	// polled 表示已经完成过至少一轮轮询；首轮不做回溯，
	// 以免桥接层每次重启都把 lookback 窗口内的读数重投一遍
	polled bool

	pollErr string
}

// New 构造桥接层。
func New(js jetstream.JetStream, lims *limsapi.Client, opts Options, log *logx.Logger) *Bridge {
	if opts.Stream == "" {
		opts.Stream = "LAB_READINGS"
	}
	if opts.SubjectPrefix == "" {
		opts.SubjectPrefix = "lab"
	}
	if opts.ConsumerPrefix == "" {
		opts.ConsumerPrefix = "bridge"
	}
	if opts.Lookback <= 0 {
		opts.Lookback = 15 * time.Minute
	}
	if opts.PollInterval <= 0 {
		opts.PollInterval = 10 * time.Second
	}
	if opts.RetryDelay <= 0 {
		opts.RetryDelay = 5 * time.Second
	}
	if opts.MaxAckPending <= 0 {
		opts.MaxAckPending = 64
	}
	return &Bridge{
		js: js, lims: lims, opts: opts, log: log,
		workers:   map[string]*worker{},
		listening: map[string]bool{},
	}
}

// Run 持续跟随 LIMS 的会话状态，阻塞直到 ctx 取消。
func (b *Bridge) Run(ctx context.Context) error {
	b.log.Infof("桥接已启动：%s → %s（会话开始前回溯 %s）",
		b.opts.Stream, b.lims.BaseURL, b.opts.Lookback)

	ticker := time.NewTicker(b.opts.PollInterval)
	defer ticker.Stop()
	defer b.stopAll()

	for {
		b.sync(ctx)
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}

// sync 拉一次会话状态，并据此启停各仪器的投递。
func (b *Bridge) sync(ctx context.Context) {
	instruments, err := b.lims.Instruments(ctx)
	if err != nil {
		if ctx.Err() == nil {
			b.setPollErr(err.Error())
			b.log.Dedupf("bridge-poll", logx.LevelWarning, "拉取 LIMS 仪器清单失败：%v", err)
		}
		return
	}
	b.setPollErr("")
	b.log.ResetDedup("bridge-poll")

	now := map[string]bool{}
	for _, ins := range instruments {
		if ins.Code != "" {
			now[ins.Code] = ins.Start
		}
	}

	b.mu.Lock()
	first := !b.polled
	b.polled = true
	previous := b.listening
	b.listening = now
	b.mu.Unlock()

	for code, on := range now {
		switch {
		case on && !b.delivering(code):
			// 首轮不回溯：续用已有 consumer 的位置，避免重启重投。
			// 之后从"没在采集"变成"在采集"，才是会话刚开，需要回溯。
			rewind := !first && !previous[code]
			b.start(ctx, code, rewind)
		case !on && b.delivering(code):
			b.stop(code, "LIMS 已停止采集")
		}
	}
	// LIMS 不再返回的仪器（模板删了、Token 换了）也要收摊
	for _, code := range b.activeCodes() {
		if _, ok := now[code]; !ok {
			b.stop(code, "LIMS 不再返回该仪器")
		}
	}
}

// start 为一台仪器建立投递。
func (b *Bridge) start(ctx context.Context, code string, rewind bool) {
	consumer, err := b.ensureConsumer(ctx, code, rewind)
	if err != nil {
		b.log.Dedupf("bridge-consumer-"+code, logx.LevelWarning,
			"[%s] 建立投递失败：%v", code, err)
		return
	}
	b.log.ResetDedup("bridge-consumer-" + code)

	w := &worker{code: code}
	cc, err := consumer.Consume(b.handler(ctx, w))
	if err != nil {
		b.log.Warnf("[%s] 启动投递失败：%v", code, err)
		return
	}
	w.consume = cc
	w.consumer = consumer

	b.mu.Lock()
	b.workers[code] = w
	b.mu.Unlock()

	if rewind {
		b.log.Infof("[%s] 会话已开始，从 %s 前的读数开始投递", code, b.opts.Lookback)
	} else {
		b.log.Infof("[%s] 恢复投递", code)
	}
}

// ensureConsumer 取得该仪器的 durable consumer。
//
// rewind 为真表示会话刚开：删掉旧 consumer 重建，把起点挪到
// "现在 − lookback"，这样既能补上会话开始前的读数，又不会把更早的
// 陈年数据一起灌进 LIMS。重投的部分由 LIMS 按 event_id 去重，不会重复入库。
func (b *Bridge) ensureConsumer(ctx context.Context, code string, rewind bool) (jetstream.Consumer, error) {
	stream, err := b.js.Stream(ctx, b.opts.Stream)
	if err != nil {
		return nil, fmt.Errorf("找不到云端读数流 %s: %w", b.opts.Stream, err)
	}
	name := b.consumerName(code)

	existing, err := stream.Consumer(ctx, name)
	switch {
	case err == nil && !rewind:
		return existing, nil
	case err == nil && rewind:
		if err := stream.DeleteConsumer(ctx, name); err != nil {
			return nil, fmt.Errorf("重置投递位置失败: %w", err)
		}
	case !errors.Is(err, jetstream.ErrConsumerNotFound):
		return nil, err
	}

	start := time.Now().Add(-b.opts.Lookback)
	return stream.CreateConsumer(ctx, jetstream.ConsumerConfig{
		Durable:       name,
		Description:   "投递到 SENAITE 的进度游标（仪器 " + code + "）",
		FilterSubject: b.subject(code),
		AckPolicy:     jetstream.AckExplicitPolicy,
		DeliverPolicy: jetstream.DeliverByStartTimePolicy,
		OptStartTime:  &start,
		AckWait:       60 * time.Second,
		MaxDeliver:    -1,
		MaxAckPending: b.opts.MaxAckPending,
	})
}

// handler 处理一条待投递读数。
func (b *Bridge) handler(ctx context.Context, w *worker) jetstream.MessageHandler {
	return func(msg jetstream.Msg) {
		reading, err := model.DecodeReading(msg.Data())
		if err != nil {
			// 解析不了的消息重投多少次都一样，直接终止投递
			b.log.Errorf("[%s] 跳过一条无法解析的消息：%v", w.code, err)
			_ = msg.Term()
			return
		}

		res := b.lims.Ingest(ctx, msg.Data())
		switch res.Outcome {
		case limsapi.Accepted:
			_ = msg.Ack()
			w.markForwarded()
			b.log.ResetDedup("bridge-ingest-" + w.code)

		case limsapi.NoSession:
			// 会话正好在这一刻关掉了：把消息退回队列并停下来，
			// 等下次「开始采集」再从这里接着投，一条都不丢。
			_ = msg.NakWithDelay(b.opts.RetryDelay)
			w.setError("LIMS 暂无监听中的会话")
			b.stop(w.code, "LIMS 暂无监听中的会话")

		case limsapi.Rejected:
			b.log.Warnf("[%s] LIMS 拒绝该读数，已放弃 %s（%s）：%s",
				w.code, reading.EventID, reading.RawText, res.Message)
			w.markSkipped(res.Message)
			_ = msg.Term()

		default:
			w.setError(res.Message)
			b.log.Dedupf("bridge-ingest-"+w.code, logx.LevelWarning,
				"[%s] 投递失败，%s 后重试：%s", w.code, b.opts.RetryDelay, res.Message)
			_ = msg.NakWithDelay(b.opts.RetryDelay)
		}
	}
}

// stop 停止一台仪器的投递；消费位置留在原地，下次开会话接着投。
func (b *Bridge) stop(code, reason string) {
	b.mu.Lock()
	w, ok := b.workers[code]
	if ok {
		delete(b.workers, code)
	}
	b.mu.Unlock()
	if !ok {
		return
	}
	w.close()
	b.log.Infof("[%s] 暂停投递（%s）", code, reason)
}

func (b *Bridge) stopAll() {
	for _, code := range b.activeCodes() {
		b.stop(code, "桥接退出")
	}
}

// Status 汇总各仪器的投递情况。
func (b *Bridge) Status(ctx context.Context) []InstrumentStatus {
	b.mu.Lock()
	listening := make(map[string]bool, len(b.listening))
	for k, v := range b.listening {
		listening[k] = v
	}
	workers := make(map[string]*worker, len(b.workers))
	for k, v := range b.workers {
		workers[k] = v
	}
	b.mu.Unlock()

	codes := map[string]struct{}{}
	for code := range listening {
		codes[code] = struct{}{}
	}
	for code := range workers {
		codes[code] = struct{}{}
	}

	out := make([]InstrumentStatus, 0, len(codes))
	for code := range codes {
		st := InstrumentStatus{Code: code, Listening: listening[code]}
		if w := workers[code]; w != nil {
			st.Delivering = true
			st.Forwarded, st.Skipped, st.LastError, st.LastForward = w.snapshot()
			if info, err := w.consumer.Info(ctx); err == nil {
				st.Pending = info.NumPending + uint64(info.NumAckPending)
			}
		}
		out = append(out, st)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Code < out[j].Code })
	return out
}

// PollError 返回最近一次拉取 LIMS 仪器清单的错误。
func (b *Bridge) PollError() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.pollErr
}

func (b *Bridge) setPollErr(msg string) {
	b.mu.Lock()
	b.pollErr = msg
	b.mu.Unlock()
}

func (b *Bridge) delivering(code string) bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	_, ok := b.workers[code]
	return ok
}

func (b *Bridge) activeCodes() []string {
	b.mu.Lock()
	defer b.mu.Unlock()
	out := make([]string, 0, len(b.workers))
	for code := range b.workers {
		out = append(out, code)
	}
	return out
}

func (b *Bridge) consumerName(code string) string {
	return b.opts.ConsumerPrefix + "-" + config.SanitizeToken(code)
}

// subject 匹配任意站点下该仪器的读数：<prefix>.*.readings.<code>
func (b *Bridge) subject(code string) string {
	return fmt.Sprintf("%s.*.readings.%s", b.opts.SubjectPrefix, config.SanitizeToken(code))
}
