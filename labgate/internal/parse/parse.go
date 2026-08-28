// Package parse 解析仪器原始输出行，提取数值与单位。
package parse

import "regexp"

// 与旧 Python 采集端 agent/parser.py 相同的启发式：
// 取第一个数字作为读数值，其后紧跟的字母序列作为单位。
// 例："ST,GS,0.9678,mg" -> ("0.9678", "mg")
var (
	numberRe = regexp.MustCompile(`-?\d+(?:\.\d+)?`)
	// 单位字符集在旧版 [a-zA-Zµ/%] 基础上补充希腊小写 mu（μ，U+03BC）
	// 与度数符号，覆盖部分仪器用 μg / °C 输出的情况。
	unitRe = regexp.MustCompile(`[a-zA-Z\x{00b5}\x{03bc}\x{00b0}/%]+`)
)

// Reading 解析一行仪器输出，返回 (值, 单位)；无法解析时返回空串。
func Reading(line string) (value, unit string) {
	loc := numberRe.FindStringIndex(line)
	if loc == nil {
		return "", ""
	}
	value = line[loc[0]:loc[1]]
	if m := unitRe.FindString(line[loc[1]:]); m != "" {
		unit = m
	}
	return value, unit
}
