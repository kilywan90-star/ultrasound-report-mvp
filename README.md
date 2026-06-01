# Ultrasound Report Voice-to-Structured-Report MVP

超声报告语音结构化系统 — 医生口述超声所见，AI 自动生成结构化超声报告。

## 功能

- 语音录入 → ASR 实时转写
- AI 结构化提取（按脏器/病灶/诊断分类）
- 逐条审核（保留/删除）
- 保存草稿 + 发送至 PACS
- 5 类超声模板（腹部/心脏/妇产/血管/小器官）
- ICD-10 编码自动标注

## 技术栈

- 后端: Python FastAPI
- 前端: 原生 HTML/CSS/JS（单文件）
- ASR: 阿里云百炼 qwen3-asr-flash
- LLM: DeepSeek V4-Flash
- 数据库: SQLite

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/kilywan90-star/ultrasound-report-mvp.git
cd ultrasound-report-mvp
```

### 2. 安装依赖

```bash
pip install -r backend/requirements.txt
```

### 3. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的阿里云百炼和 DeepSeek API Key
```

### 4. 启动服务

```bash
cd backend
python main.py
```

浏览器打开 `http://localhost:8700`

## 使用流程

1. 左侧录入患者（姓名/性别/年龄/检查类型）
2. 点击选中患者
3. 点击录音按钮开始口述超声所见
4. 点击转写语音 → 查看原始文本
5. 点击结构化提取 → 查看逐条审核卡片
6. 逐条审核：保留对的、删除不需要的
7. 保存草稿 → 可继续修改
8. 发送至 PACS → 最终确认

## 键盘快捷键

| 快捷键 | 功能 |
|------|------|
| `Ctrl+R` | 开始/停止录音 |
| `Ctrl+P` | 暂停/继续 |
| `Ctrl+S` | 保存草稿 |
| `Ctrl+Enter` | 发送至PACS |
| `Esc` | 清空工作区 |

## 项目结构

```
ultrasound-report-mvp/
├── backend/
│   ├── main.py          # FastAPI 服务
│   ├── db.py             # SQLite 数据库
│   ├── llm_client.py     # DeepSeek 结构化提取
│   ├── asr_client.py     # 阿里云百炼语音识别
│   ├── templates.py      # 5 类超声模板
│   ├── requirements.txt
│   └── test_100.py       # 100 条批量测试脚本
├── frontend/
│   └── index.html        # 单页应用
├── .env.example
└── README.md
```

## License

MIT
