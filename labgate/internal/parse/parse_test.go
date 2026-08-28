package parse

import "testing"

func TestReading(t *testing.T) {
	cases := []struct {
		name      string
		line      string
		wantValue string
		wantUnit  string
	}{
		{"梅特勒稳定读数", "ST,GS,0.9678,mg", "0.9678", "mg"},
		{"带正负号", "ST,NT,-12.34,g", "-12.34", "g"},
		{"值单位之间有空格", "  1.2345 kg  ", "1.2345", "kg"},
		{"无单位", "42", "42", ""},
		{"整数带单位", "100g", "100", "g"},
		{"微克 micro sign", "0.5µg", "0.5", "µg"},
		{"微克 希腊字母 mu", "0.5μg", "0.5", "μg"},
		{"温度", "T: 36.6 °C", "36.6", "°C"},
		{"百分比", "湿度 55 %", "55", "%"},
		{"带斜杠单位", "3.2 mg/L", "3.2", "mg/L"},
		{"没有数字", "ERROR: overload", "", ""},
		{"空行", "", "", ""},
		// 启发式的已知局限：型号里的数字会被当成读数值。
		// 这类仪器需要在云端按模板重新解析，采集端只保证原始行不丢。
		{"型号中的数字会被误取", "CH1 0.500 mg", "1", "mg"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			value, unit := Reading(tc.line)
			if value != tc.wantValue || unit != tc.wantUnit {
				t.Errorf("Reading(%q) = (%q, %q), 期望 (%q, %q)",
					tc.line, value, unit, tc.wantValue, tc.wantUnit)
			}
		})
	}
}
