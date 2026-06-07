# 超声语音报告系统 — 架构文档

> v3.3.20260607 — 2026-06-08

---

## 一、项目概览

```
ultrasound-report-mvp/
├── backend/               # FastAPI 后端 (核心)
│   ├── main.py            # 应用入口 (147行)
│   ├── main_v3.py         # 替代入口 (87行，另用 routers/*)
│   ├── routers/           # API 路由模块
│   ├── validators/        # 验证工具
│   ├── templates.py       # 70条基础模板
│   ├── template_loader.py # 340条 CSV 模板加载器
│   ├── template_converted/ # 464 条转换模板 (abdomen, thyroid, breast 等)
│   ├── match_engine.py    # 40万数据匹配引擎
│   ├── engine.py          # 桌面规则库匹配引擎 v3.1
│   ├── asr_*.py           # ASR服务 (aliyun+whisper)
│   ├── llm_client.py      # LLM 客户端 (火山方舟 doubao)
│   ├── knowledge/         # 57个知识库 JSON
│   ├── db.py              # 数据库层 (report/patient 操作)
│   ├── database.py        # 数据库层 (另一套 schema，用于 main_v3)
│   ├── tests/             # 回归测试
│   └── scripts/           # 工具/基准脚本
├── frontend/              # 8个 HTML 前端页面
├── microservice/          # 微服务 (audio_filter, audit_logger 等)
├── docs/                  # 本文档
├── Dockerfile             # 容器化部署
└── docker-compose.yml
```

---

## 二、路由架构

### 入口文件

```
main.py (147行)
├── .env 加载
├── app = FastAPI()
├── CORS + 安全中间件 + API认证中间件
├── api_* 外部接口路由 (6个: pacs, section_templates, syslog 等)
├── 新拆分路由 (5个路由器)
│   ├── routers/structure.py      → /api/structure (核心管线)
│   ├── routers/fixed_template.py  → /api/fixed-template/*, /api/template/*
│   ├── routers/audio.py           → /api/audio/*, /api/transcribe
│   ├── routers/quick_patients.py  → /api/patients/quick-add, queue, status
│   └── routers/main_reports.py    → /api/reports/*CRUD
├── GET /api/health
├── GET /api/templates (70条模板列表)
├── 静态文件服务
└── if __name__ == "__main__" (uvicorn)
```

### 路由模块

| 文件 | 路由 | 说明 |
|------|------|------|
| `routers/structure.py` | `/api/structure` | **核心管线** — ASR校正→路由→模板匹配→LLM填充→验证 |
| `routers/fixed_template.py` | `/api/fixed-template/*` | 固定模板意图识别+标签 |
| `routers/audio.py` | `/api/audio/*`, `/api/transcribe` | 音频上传/转写/回放 |
| `routers/quick_patients.py` | `/api/patients/quick-add` 等 | 患者快捷操作 |
| `routers/main_reports.py` | `/api/reports/*` | 报告CRUD（使用 db.py 层） |
| `routers/voice.py` | `/api/voice/*` | [main_v3] 全量语音管线 |
| `routers/patients.py` | `/api/patients/*` | [main_v3] 患者管理 |
| `routers/reports.py` | `/api/reports/*` | [main_v3] 报告管理（使用 database.py） |

> **注意**: `routers/reports.py` 与 `routers/main_reports.py` 都监听 `/api/reports/` 路径但使用不同数据层。`main.py` 只加载 `main_reports.py`，`main_v3.py` 只加载 `reports.py`，不会冲突。

---

## 三、核心管线路由 (`/api/structure`)

### 流程

```
ASR文本输入
    │
    ▼
L0. 文本长度门控
L0.5 口误检测 (不对不对→保留第二值)
    │
    ▼
路由预分类 (routing/__init__.py)
    ├── 12类路由: fetal, cardiac, thyroid, breast, abdomen...
    ├── is_fetal? → 胎儿快速路径 (fill_fetal_template)
    ├── is_multi? → LLM多器官填充
    └── else → 模板匹配
              │
              ▼
        模板搜索 (template_loader)
            ├── category 过滤 → 按器官限搜索范围
            ├── 得分偏低? → 跨类别保底
            ├── 40万数据引擎补充
            └── 多候选模板智能选择
              │
              ▼
        路径分派
            ├── converted_fill (464转换模板, 得分≥100)
            │   ├── → 填充
            │   └── unfill过多? → LLM补全
            ├── rule_fill (规则填充, 得分≥200)
            ├── template_fill (LLM填充, 得分≥50)
            └── llm_free (无匹配)
              │
              ▼
        数值保全 (ASR数字→报告)
        LLM建议生成 (规则优先, LLM兜底)
        多器官兜底
        保存到 DB + trace 日志
```

### 辅助函数位置

| 函数 | 位置 |
|------|------|
| `_generate_recommendation` | `routers/structure.py` |
| `_llm_fill_template` | `routers/structure.py` |
| `_llm_complete_report` | `routers/structure.py` |
| `_llm_multi_organ_fill` | `routers/structure.py` |
| `_llm_free_generate` | `routers/structure.py` |
| `_preserve_numbers` | `routers/structure.py` |
| `detect_sex_conflict` | `validators/patient.py` |
| `detect_pregnancy_conflict` | `validators/patient.py` |

---

## 四、知识库体系

| 位置 | 内容 | 数量 |
|------|------|------|
| `backend/knowledge/` | JSON 知识库文件 | 57 个 |
| `backend/knowledge/1长沙范本.csv` | CSV 模板源 | 340 条 |
| `backend/knowledge/40w_match_index.json` | 40万数据匹配索引 | 57478 条 |
| `backend/template_converted/` | 转换模板 (abdomen, thyroid 等) | 464 条 |
| `backend/knowledge/超声规则库_rulebase.json` | 桌面规则库副本 | - |

各 JSON 文件用途：

| 文件 | 用途 |
|------|------|
| `confusion_dict.json` | ASR 混淆词纠正 (前列腺→前列县) |
| `hotwords.json` | Whisper 热词提示 |
| `dialect_mapping.json` | 方言映射表 |
| `master_rules.json` | 主规则库 |
| `template_fields.json` | 模板字段定义 (1.1MB) |
| `template_tags_v2.json` | 模板分类标签 |
| `normal_ranges.json` | HIS 正常值范围 |
| `normal_thresholds.json` | 数值阈值 |
| `antonym_pairs.json` | 反义词对 (矛盾检测) |
| `...` | 共 57 个文件 |

---

## 五、数据层

`backend/` 有两套数据层：

| | db.py | database.py |
|--|-------|-------------|
| **路由** | `main.py` + `routers/` 新文件 | `main_v3.py` + 旧 `routers/*` |
| **DB** | `ultrasound.db` | `ultrasound.db` |
| **reports 表** | 8列 (简版) | 24列 (全量) |
| **连接方式** | `threading.local()` | 每次 `get_db()` 新连接 |

---

## 六、外部服务

| 服务 | 用途 | 配置位置 |
|------|------|----------|
| 阿里云 Bailian ASR | `qwen3-asr-flash` 云端语音识别 | `.env` DASHSCOPE_API_KEY |
| 火山方舟 | `doubao-seed-1-6-flash` LLM 报告生成 | `.env` VOLC_* |
| Whisper | 本地 ASR 兜底 | `asr_service.py` |
| HTTPS | 自签名 cert+key (语音识别需要安全上下文) | `key.pem` + `cert.pem` |

---

## 七、关键词索引

```
回归测试:  cd backend && python tests/test_regression.py
启动:      cd backend && python main.py
启动v3:    cd backend && python main_v3.py
端口:      main.py=8700 (HTTPS), main_v3.py=18001
知识库:    backend/knowledge/
模板CSV:   backend/knowledge/1长沙范本.csv
```
