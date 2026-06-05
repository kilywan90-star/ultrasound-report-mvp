<!-- xiaozhi.me MCP 配置说明 -->

## 超声报告语音结构化 MCP Server

### 方式一: stdio 模式 (推荐)

在 xiaozhi.me 控制台 → MCP接入点 → 新建:

| 配置项 | 值 |
|--------|-----|
| 名称 | 超声报告语音结构化 |
| 传输协议 | stdio |
| 命令 | python3 |
| 参数 | /opt/ultrasound-report-mvp/ultrasound_mcp_server.py |
| 工作目录 | /opt/ultrasound-report-mvp |

### 方式二: HTTP 外部工具

| 配置项 | 值 |
|--------|-----|
| URL | http://47.109.151.238:8800/v1/mcp/transcribe |
| Method | POST |
| Content-Type | application/json |

参数:
- audio_base64 (string, 必填) — base64编码的音频
- patient_id (string, 必填) — 病历号
- gender (string, 必填) — 男/女
- age (integer, 必填) — 年龄 0-150
- exam_type (string, 必填) — 检查类型
- name (string, 可选) — 患者姓名

### 使用

配置完成后, 对小智机器人说:

"小智小智, 开始超声报告"

→ 小智录音 → MCP调超声API → 返回结构化报告 → TTS朗读结果
