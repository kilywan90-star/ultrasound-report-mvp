# 超声报告语音结构化系统 — 会话摘要 v3.3
> 更新: 2026-06-08 23:30
> 版本: v3.3.20260607-2103

## 一、部署

```
用户 → HTTP:80 → Nginx → HTTPS:443 → uvicorn:9999 → FastAPI
服务器: 47.109.151.238 (CPU 2核, RAM 3.4GB, 无GPU)
服务: ultrasound-web.service ✅
```

## 二、微调模型

```
训练: Qwen2.5-3B + Q-LoRA (2000条, 1 epoch, GPU 4070S)
merged model: backend/scripts/ultrasound-ft-model/merged/ (5.8GB)
推理引擎: backend/llm_local.py  (generate / generate_structured)
推理速度: ~5.5s/条
开关: routers/structure.py L21 → _USE_LOCAL_LLM = True/False
```

## 三、测试结果

| 测试 | 成功 | 直填 | LLM |
|------|------|------|-----|
| 100条 | 100% | 76% (0.02s) | 24% (6.7s) |
| 1000条自动 | 100% | 68.5% (0.03s) | 31.5% |
| 1000条真实格式 | 99.7% | 57.7% (0.03s) | 42% (1.04s) |
| 数值补充 | 565条触发 | 已修复 | - |

## 四、已修复

1. 路由2 category过滤真正生效
2. Nginx HTTP→HTTPS + 录音安全上下文
3. 3个路由匹配(肝内钙化灶/子宫内膜/胆囊炎)
4. 10个匹配偏差(胰腺/脾脏/未见否定)
5. 数值补充测量(converted_fill数值保全)

## 五、待办

- WSL2 + vLLM (需重启)
- 全量训练50000条
- 前端优化
- 方言扩展
