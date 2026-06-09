"""
超声报告系统 — 本地 LoRA 模型推理引擎
替代火山方舟 Doubao，使用本地 Qwen2.5 + LoRA 适配器

环境要求:
  pip install transformers peft torch accelerate

模型路径:
  merged/ — 融合模型（直接加载）
  final/  — LoRA 适配器（需配合 Qwen2.5-3B-Instruct 基座）
"""

import json, re, os, logging, time
from pathlib import Path

# ===== 配置 =====
MODEL_DIR = Path(os.environ.get(
    "LOCAL_LLM_PATH",
    r"E:\claude\ultrasound-ft-model-archive\ultrasound-ft-model-trash"
))
MERGED_PATH = MODEL_DIR / "merged"
LORA_PATH = MODEL_DIR / "final"
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"

_DEVICE = "auto"
_MODEL = None
_TOKENIZER = None


def load_model():
    global _MODEL, _TOKENIZER
    if _MODEL is not None:
        return _MODEL, _TOKENIZER

    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    if MERGED_PATH.exists():
        print(f"[本地LLM] 加载融合模型: {MERGED_PATH}")
        _TOKENIZER = AutoTokenizer.from_pretrained(str(MERGED_PATH), trust_remote_code=True)
        _MODEL = AutoModelForCausalLM.from_pretrained(
            str(MERGED_PATH), device_map=_DEVICE, trust_remote_code=True,
            torch_dtype=torch.float16,
        )
    else:
        print(f"[本地LLM] 加载基座: {BASE_MODEL}")
        _TOKENIZER = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
        base = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL, device_map=_DEVICE, trust_remote_code=True,
            torch_dtype=torch.float16,
        )
        from peft import PeftModel
        print(f"[本地LLM] 加载 LoRA: {LORA_PATH}")
        _MODEL = PeftModel.from_pretrained(base, str(LORA_PATH))

    _MODEL.eval()
    print(f"[本地LLM] 就绪")
    return _MODEL, _TOKENIZER


def _infer(prompt: str, system_prompt: str = "", max_tokens: int = 2048, temperature: float = 0.1) -> str:
    model, tokenizer = load_model()
    import torch

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs, max_new_tokens=max_tokens,
            temperature=temperature, top_p=0.9, do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )

    return tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()


def generate(prompt: str, system_prompt: str = "", max_tokens: int = 2048) -> str:
    return _infer(prompt, system_prompt, max_tokens)


def generate_structured(system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict:
    t0 = time.time()
    raw = _infer(user_prompt, system_prompt, max_tokens, temperature=0.05)
    elapsed = time.time() - t0

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    if "<div" in raw or "study_see" in raw[:200]:
        html = re.search(r'<div[^>]*class=.rpt-html.*?>.*?</div>', raw, re.DOTALL)
        if html:
            return {"study_see": html.group(0), "study_hint": [], "recommendation": ""}

    return {"study_see": f"<div class='rpt-html'>{raw[:2000]}</div>", "study_hint": [], "recommendation": ""}


def generate_free_report(asr_text: str, exam_type: str) -> dict:
    system = f"你是一位超声科主任医师。将口述转为规范化超声报告。检查类型: {exam_type}"
    prompt = f"请根据以下口述生成完整超声报告:\n\n{asr_text[:2000]}"
    return generate_structured(system, prompt, max_tokens=4096)
