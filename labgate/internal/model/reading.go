// Package model 定义采集端与云端之间流转的数据契约。
package model

import (
	"encoding/json"
	"time"
)

// Parsed 是从原始行中解析出的结构化读数。
type Parsed struct {
	Value  string `json:"value"`
	Unit   string `json:"unit"`
	Stable bool   `json:"stable"`
}

// Reading 是一条仪器读数事件。
//
// 字段与旧 Python 采集端推送 SENAITE @@instrument_acquisition_api_ingest
// 的请求体保持一致（event_id / instrument_code / received_at / raw_text /
// parsed），云端可直接复用；site_id 为新增字段，供云端区分实验室站点，
// 旧接口会忽略它。
type Reading struct {
	EventID        string `json:"event_id"`
	SiteID         string `json:"site_id,omitempty"`
	InstrumentCode string `json:"instrument_code"`
	ReceivedAt     string `json:"received_at"`
	RawText        string `json:"raw_text"`
	Parsed         Parsed `json:"parsed"`
}

// TimeFormat 是 received_at 的格式（与旧采集端一致，本地时间无时区后缀）。
const TimeFormat = "2006-01-02T15:04:05"

// NewReading 用当前时间组装一条读数事件。
func NewReading(eventID, siteID, code, raw, value, unit string) Reading {
	return Reading{
		EventID:        eventID,
		SiteID:         siteID,
		InstrumentCode: code,
		ReceivedAt:     time.Now().Format(TimeFormat),
		RawText:        raw,
		Parsed:         Parsed{Value: value, Unit: unit, Stable: true},
	}
}

// Encode 序列化为 NATS 消息体 / HTTP 请求体。
func (r Reading) Encode() ([]byte, error) { return json.Marshal(r) }

// DecodeReading 从 NATS 消息体还原读数事件。
func DecodeReading(data []byte) (Reading, error) {
	var r Reading
	err := json.Unmarshal(data, &r)
	return r, err
}
