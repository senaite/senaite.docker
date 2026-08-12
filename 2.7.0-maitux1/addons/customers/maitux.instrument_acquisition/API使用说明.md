# 仪器数据采集HTTP转发API使用说明

## 功能概述

本API为SENAITE仪器数据采集插件提供HTTP二次转发功能，支持将解析后的仪器数据自动转发到指定的HTTP接口。

## 新增功能

### 1. 模板配置扩展

在仪器解析模板中新增以下HTTP转发配置字段：

- **Enable HTTP Forward** (forward_enabled): 是否启用HTTP转发
- **Forward URL** (forward_url): 目标HTTP接口地址
- **HTTP Method** (forward_method): 请求方法 (POST/PUT)
- **HTTP Headers (JSON)** (forward_headers): 自定义HTTP头，JSON格式
- **Timeout (seconds)** (forward_timeout): 请求超时时间，默认30秒

### 2. 转发数据格式

转发到目标接口的数据格式：

```json
{
  "timestamp": "2024-01-01T12:00:00.000000",
  "template_uid": "template-uid",
  "template_title": "模板名称",
  "instrument_uid": "instrument-uid",
  "instrument_title": "仪器名称",
  "raw_data": "原始仪器数据",
  "parsed_data": "解析后的数据（JSON对象或字符串）"
}
```

## API接口

### 1. 获取模板列表

**接口**: `@@instrument_acquisition_api_templates_list`

**方法**: GET

**示例**:
```
GET /@@instrument_acquisition_api_templates_list
```

**响应**:
```json
{
  "success": true,
  "templates": [
    {
      "uid": "template-1-uid",
      "title": "模板1",
      "url": "http://.../template-1"
    }
  ]
}
```

### 2. 获取转发状态

**接口**: `@@instrument_acquisition_api_forward_status`

**方法**: GET

**参数**:
- `uid`: 模板UID

**示例**:
```
GET /@@instrument_acquisition_api_forward_status?uid=template-uid
```

**响应**:
```json
{
  "success": true,
  "template": {
    "uid": "template-uid",
    "title": "模板名称",
    "forward_enabled": true,
    "forward_url": "http://example.com/api/data",
    "forward_method": "POST",
    "forward_timeout": 30
  },
  "forwarder": {
    "is_enabled": true,
    "queue_size": 0
  }
}
```

### 3. 测试转发

**接口**: `@@instrument_acquisition_api_forward_test`

**方法**: GET

**参数**:
- `uid`: 模板UID
- `raw_data`: 测试原始数据（可选）
- `parsed_data`: 测试解析数据，JSON格式（可选）

**示例**:
```
GET /@@instrument_acquisition_api_forward_test?uid=template-uid&raw_data=TEST123&parsed_data={"test":"value"}
```

**响应**:
```json
{
  "success": true,
  "message": "HTTP 200 - OK",
  "test_data": {
    "raw": "TEST123",
    "parsed": {"test": "value"}
  }
}
```

### 4. 获取转发历史

**接口**: `@@instrument_acquisition_api_forward_history`

**方法**: GET

**参数**:
- `uid`: 模板UID
- `limit`: 返回记录数量，默认10（可选）

**示例**:
```
GET /@@instrument_acquisition_api_forward_history?uid=template-uid&limit=20
```

**响应**:
```json
{
  "success": true,
  "history": [
    {
      "timestamp": "2024-01-01T12:00:00.000000",
      "url": "http://example.com/api/data",
      "method": "POST",
      "success": true,
      "status_code": 200,
      "message": "HTTP 200 - OK"
    }
  ],
  "queue_size": 0
}
```

### 5. 手动转发数据

**接口**: `@@instrument_acquisition_api_manual_forward`

**方法**: POST

**参数** (Query String):
- `uid`: 模板UID

**请求体** (JSON):
```json
{
  "raw_data": "原始数据字符串",
  "parsed_data": {"key": "value"}
}
```

**示例**:
```bash
curl -X POST \
  "http://site/@@instrument_acquisition_api_manual_forward?uid=template-uid" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_data": "TEST_DATA",
    "parsed_data": {"result": "positive"}
  }'
```

**响应**:
```json
{
  "success": true,
  "message": "HTTP 200 - OK",
  "data": {
    "raw": "TEST_DATA",
    "parsed": {"result": "positive"}
  }
}
```

## 使用步骤

1. **配置转发**: 在仪器解析模板中启用HTTP转发并配置目标URL
2. **启动服务**: 启动仪器数据采集服务
3. **接收数据**: 仪器连接并发送数据
4. **自动转发**: 系统自动将解析后的数据转发到配置的接口

## 自定义HTTP头示例

如需添加认证token或其他自定义头，可以在"HTTP Headers (JSON)"字段中配置：

```json
{
  "Authorization": "Bearer your-token-here",
  "X-Custom-Header": "custom-value"
}
```

## 注意事项

1. 确保已安装requests库 (`pip install requests`)
2. 目标接口应能正确处理JSON格式的POST/PUT请求
3. 转发失败不会影响数据采集的正常流程
4. 转发采用异步方式，不会阻塞数据接收
