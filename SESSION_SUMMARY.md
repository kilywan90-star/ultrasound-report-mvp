超声报告语音结构化系统 — 会话摘要
============================================

## 项目信息
- 名称: 超声报告语音结构化系统
- 版本: v3.0-ABCDEF 超声绿版 (方言适配)
- 部署: https://47.109.151.238 | http://47.109.151.238:9999
- 代码位置: E:\claude\ultrasound-report-mvp\
- 服务器: root@47.109.151.238 (sql2k8!WF)
- 服务自动热重载 (--reload), 系统crond每15分钟自动修复

## 核心架构
### 流水线 (8阶段)
Stage 1: 音频过滤 (<0.5s=无效)
Stage 2: ASR转写 (阿里百炼 qwen3-asr-flash)
Stage 3: ASR纠错 + 文本长度门 (>=20字)
Stage 4: 冲突检测 (性别/妊娠)
Stage 5: 模板匹配(D-path) + confidence_pct (>=90% HIGH)
Stage 5.5: 规则引擎预检 (数值范围)
Stage 6a: HIGH→模板填充保留占位符+追加 (Fill Engine v3)
Stage 6b: LOW→LLM增强 (Few-Shot + 方言规则)
Stage 7: 后置验证 (矛盾+数值+填空)
Stage 8: 异步审计日志 (audit.db)

### 模板匹配引擎 (template_anchor.py)
- P0: match_keywords (968个) 匹配 → 300分
- P1: 标签名精确匹配 → 200+分
- P2: 器官+疾病组合匹配 → 40分
- P3: 正常模式/异常模式扣分 → ±200分
- P4: 检查类型关键词匹配 → 50-60分
- P5: 器官-异常词关联矩阵(15器官,1710真实报告) → +90分
- P6: 跨类型防护(精确版) → -150分
- 置信度: >=90% HIGH直接填充, <90% LLM增强

### 关键文件
- backend/template_anchor.py — D-path引擎+评分系统
- backend/template_fill_anchored.py — 填充引擎v3 (数值100%保留)
- backend/llm_client.py — DeepSeek API (含19个Few-Shot+35条方言规则)
- backend/coverage_analyzer.py — 自动诊断+自动修复
- microservice/ — 独立微服务(端口8800, 含熔断/审计/音频过滤)
- backend/knowledge/llm_fewshot_examples_v2.json — 19个案例
- backend/knowledge/asr_hotwords_auto.json — 670个热词
- extension/ — Chrome扩展

## 关键数据资产
- 模板: 4871条, 968 match_keywords, 963 tags
- 真实报告: 2报告内容.csv(3067条), 报告结果表.csv(6830条)
- 测试: test_sample_1000.csv(1000条)

## 当前精度
- 规则引擎: ~92-95% HIGH置信
- 测试基准: 13/13 HIGH = 100%
- LLM分流: 正常报告->规则填充, 复杂报告->LLM增强
- 要达98%: 需要P7(数值交叉验证) + P8(医生反馈自学习)

## 三个精度调优层
1. 关键词层: coverage_analyzer.py --fix 自动补全
2. 阈值层: template_anchor.py line 144 分级阈值
3. Few-Shot层: llm_fewshot_examples_v2.json 加案例
