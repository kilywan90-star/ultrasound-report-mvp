"""本地微调模型推理引擎 — 替代火山方舟LLM调用"""
import os, time, logging
from pathlib import Path

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
_HERE = Path(__file__).resolve().parent
MERGED_PATH = str(_HERE / "scripts/ultrasound-ft-model/merged")

_model = None
_tokenizer = None
_loaded = False

SYSTEM_PROMPT = "你是一位超声科主任医师。根据口述超声描述，生成完整的结构化超声报告。"


def _ensure_loaded():
    global _model, _tokenizer, _loaded
    if _loaded:
        return
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    t0 = time.time()
    print(f"[本地LLM] 加载merged model...", flush=True)
    _model = AutoModelForCausalLM.from_pretrained(
        MERGED_PATH, device_map="auto", torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )
    _tokenizer = AutoTokenizer.from_pretrained(MERGED_PATH, trust_remote_code=True)
    if _tokenizer.pad_token is None:
        _tokenizer.pad_token = _tokenizer.eos_token
    _model.eval()
    _loaded = True
    print(f"[本地LLM] 加载完成 ({time.time()-t0:.1f}s)", flush=True)


def generate(prompt: str, system_prompt: str = None, max_tokens: int = 256) -> str:
    """生成文本，返回纯文本"""
    _ensure_loaded()
    import torch
    sp = system_prompt or SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": sp},
        {"role": "user", "content": prompt},
    ]
    input_text = _tokenizer.apply_chat_template(messages, tokenize=False)
    inputs = _tokenizer(input_text, return_tensors="pt").to("cuda")

    with torch.no_grad():
        outputs = _model.generate(
            **inputs, max_new_tokens=max_tokens,
            temperature=0.1, top_p=0.9, repetition_penalty=1.05,
            use_cache=True,
        )
    response = _tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    return response.strip()


def generate_structured(prompt: str, system_prompt: str = None) -> dict:
    """生成JSON结构化的报告"""
    import json, re
    text = generate(prompt, system_prompt, max_tokens=512)

    # 清理可能的 markdown 代码块和 assistant 前缀
    text = re.sub(r'```(?:json)?\s*', '', text).strip()
    text = re.sub(r'^assistant\s*\n?', '', text).strip()
    text = re.sub(r'\n```$', '', text).strip()
    text = re.sub(r'^```\n?', '', text).strip()

    # 直接JSON解析
    if text.startswith('{'):
        try:
            return json.loads(text)
        except:
            pass

    # 尝试提取JSON对象 {}
    try:
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except:
        pass
    # 兜底: 把文本作为study_see
    return {"study_see": f"<div class='rpt-html'>{text}</div>", "study_hint": [], "recommendation": ""}


def get_model_info() -> dict:
    return {
        "loaded": _loaded,
        "model": "Qwen2.5-3B-Instruct (merged+LoRA)",
        "path": MERGED_PATH,
    }


if __name__ == "__main__":
    # 快速测试
    t0 = time.time()
    output = generate("甲状腺右叶见0.5×0.3cm低回声结节，边界清")
    print(f"输出 ({time.time()-t0:.1f}s):")
    print(output[:200])
