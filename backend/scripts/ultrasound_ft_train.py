#!/usr/bin/env python3
"""超声报告结构化 — Qwen2.5-3B Q-LoRA 微调训练脚本

硬件: RTX 4070 Super (12GB VRAM)
模型: Qwen2.5-3B-Instruct (Q-LoRA 4bit, 约5GB)
数据: 40万超声报告 (全字段40万-matching_result_clean.csv)
"""

import os, sys, re, json, math, gc, random
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
CSV_PATH = r"C:\Users\Administrator\Desktop\40万超声数据挖掘\全字段40万-matching_result_clean.csv"
OUTPUT_DIR = _HERE / "ultrasound-ft-model"
OUTPUT_DIR.mkdir(exist_ok=True)

MODEL_NAME = "Qwen/Qwen2.5-3B-Instruct"
MAX_SAMPLES = 50000      # 训练用50K条 (4070S 12GB)
VAL_RATIO = 0.05         # 5% 验证集
MAX_LENGTH = 1024        # 最大序列长度
BATCH_SIZE = 4           # 12GB可跑 batch=4
GRAD_ACCUM = 4           # 梯度累积 → 有效batch 16
LR = 2e-4
EPOCHS = 2
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
SAVE_STEPS = 50   # demo (2000条): 114步, 约每10min存一次; full (50000条): ~2850步
EVAL_STEPS = 50
assert SAVE_STEPS % EVAL_STEPS == 0, f"SAVE_STEPS({SAVE_STEPS})不是EVAL_STEPS({EVAL_STEPS})的整数倍"

# ─── Data Preparation ──────────────────────────────────────────
def load_reports(csv_path, max_samples=50000):
    """加载CSV, 返回list of dict"""
    import csv as _csv
    print(f"[数据] 加载: {csv_path}")
    with open(csv_path, 'r', encoding='gbk') as f:
        content = f.read()
    fixed = re.sub(r'"[^"]*"', lambda m: m.group(0).replace('\n', ' '), content)
    reader = _csv.DictReader(fixed.splitlines())

    reports = []
    for i, row in enumerate(reader):
        if i >= max_samples:
            break

        # 兼容中英文列名
        def _get(keys, fallback=''):
            for k in keys:
                v = row.get(k)
                if v and v.strip():
                    return v.strip()
            return fallback

        see = _get(['rpt_StudySee超声所见（精简版）', 'rpt_StudySee'])
        see_full = _get(['rpt_StudySee_Full超声所见（完整版）', 'rpt_StudySee_Full'])
        discname = _get(['discname 诊断名称', 'discname'])
        discgroup = _get(['discgroup 诊断分组', 'discgroup'])
        info1 = _get(['tpl_INFO1 模板扩展信息 1', 'tpl_INFO1'])
        match_score = _get(['match_score匹配得分'])

        # 过滤: 必须有所见+诊断
        if not see or len(see) < 10 or not discname:
            continue

        reports.append({
            'see': see,
            'see_full': see_full or see,
            'discname': discname,
            'discgroup': discgroup,
            'info1': info1,
            'score': match_score,
        })

    print(f"[数据] 加载完成: {len(reports)} 条报告")
    return reports


def format_training_pair(report):
    """构造 Qwen 训练对话对

    Input:  简短超声描述 (模拟ASR输入)
    Output: 完整结构化报告
    """
    input_text = report['see']
    if len(input_text) > 300:
        input_text = input_text[:300]

    # 构造诊断文本
    hints = report['discname']
    group = report['discgroup']
    if group and group not in ('0', 'NULL', ''):
        hints = f"{group}: {hints}"

    # 输出: 结构化所见 + 提示
    output_text = f"【超声所见】\n{report['see_full']}\n\n【超声提示】\n{hints}"

    if report['info1'] and len(report['info1']) > 10:
        output_text += f"\n\n【参考模板】\n{report['info1']}"

    return input_text, output_text


def create_dataset(reports):
    """构造训练集 (Qwen 对话格式)"""
    from datasets import Dataset

    inputs, outputs = [], []
    for r in reports:
        inp, out = format_training_pair(r)
        inputs.append(inp)
        outputs.append(out)

    data = {"input": inputs, "output": outputs}
    return Dataset.from_dict(data)


def tokenize_fn(examples, tokenizer):
    """Tokenize 对话对"""
    texts = []
    for inp, out in zip(examples["input"], examples["output"]):
        # Qwen 聊天模板
        messages = [
            {"role": "system", "content": "你是一位超声科主任医师。根据口述超声描述，生成完整的结构化超声报告。"},
            {"role": "user", "content": inp},
            {"role": "assistant", "content": out},
        ]
        text = tokenizer.apply_chat_template(messages, tokenize=False)
        texts.append(text)

    tokenized = tokenizer(
        texts,
        truncation=True,
        padding="max_length",
        max_length=MAX_LENGTH,
        return_tensors=None,
    )

    # labels = input_ids (用于计算loss)
    tokenized["labels"] = tokenized["input_ids"].copy()
    return tokenized


# ─── Model Loading (Q-LoRA) ────────────────────────────────────
def load_model_and_tokenizer():
    """加载 Qwen2.5-3B + 4bit Q-LoRA"""
    import torch
    from transformers import (
        AutoModelForCausalLM, AutoTokenizer,
        BitsAndBytesConfig, TrainingArguments
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    # 4bit 量化配置
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    print(f"[模型] 加载: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_NAME,
        trust_remote_code=True,
        padding_side="right",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )

    # 准备 k-bit 训练
    model = prepare_model_for_kbit_training(model)

    # LoRA 配置
    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                       "gate_proj", "up_proj", "down_proj"],
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    return model, tokenizer


# ─── Training ──────────────────────────────────────────────────
def train():
    import torch
    from transformers import TrainingArguments, Trainer, DataCollatorForSeq2Seq

    # ── 数据 ──
    reports = load_reports(CSV_PATH, MAX_SAMPLES)
    random.shuffle(reports)

    n_val = max(1, int(len(reports) * VAL_RATIO))
    train_reports = reports[n_val:]
    val_reports = reports[:n_val]
    print(f"[数据] 训练: {len(train_reports)} 验证: {len(val_reports)}")

    # ── 模型 ──
    model, tokenizer = load_model_and_tokenizer()

    # ── 数据集 ──
    train_ds = create_dataset(train_reports)
    val_ds = create_dataset(val_reports)

    train_ds = train_ds.map(lambda x: tokenize_fn(x, tokenizer), batched=True)
    val_ds = val_ds.map(lambda x: tokenize_fn(x, tokenizer), batched=True)

    # 移除原始文本列
    remove_cols = [c for c in train_ds.column_names if c in ("input", "output")]
    train_ds = train_ds.remove_columns(remove_cols)
    val_ds = val_ds.remove_columns(remove_cols)

    # ── 训练参数 ──
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR / "checkpoints"),
        overwrite_output_dir=True,
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        learning_rate=LR,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        bf16=True,
        logging_steps=20,
        save_steps=SAVE_STEPS,
        eval_steps=EVAL_STEPS,
        eval_strategy="steps",
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to="none",
        ddp_find_unused_parameters=False,
        remove_unused_columns=True,
    )

    data_collator = DataCollatorForSeq2Seq(
        tokenizer, pad_to_multiple_of=8, return_tensors="pt"
    )

    # ── 训练 ──
    trainer = Trainer(
        model=model,
        args=training_args,
        data_collator=data_collator,
        train_dataset=train_ds,
        eval_dataset=val_ds,
    )

    print("\n" + "="*60)
    print("  开始训练 Qwen2.5-3B + Q-LoRA")
    print(f"  训练: {len(train_ds)} 条, 验证: {len(val_ds)} 条")
    print(f"  Epochs: {EPOCHS}, Batch: {BATCH_SIZE}, Accum: {GRAD_ACCUM}")
    print(f"  Max Length: {MAX_LENGTH}, LoRA r: {LORA_R}")
    print(f"  GPU: RTX 4070 Super (12GB VRAM)")
    print(f"  Save every: {SAVE_STEPS} steps")

    trainer.train()

    # ── 保存最终模型 ──
    final_path = OUTPUT_DIR / "final"
    final_path.mkdir(exist_ok=True)
    trainer.save_model(str(final_path))
    tokenizer.save_pretrained(str(final_path))
    print(f"[完成] 完整模型保存到: {final_path}")

    # LoRA adapter only
    adapter_path = OUTPUT_DIR / "adapter"
    adapter_path.mkdir(exist_ok=True)
    model.save_pretrained(str(adapter_path))
    print(f"[完成] LoRA adapter保存到: {adapter_path}")

    return model, tokenizer


# ─── Inference Demo ────────────────────────────────────────────
def inference_demo(model_path=None):
    """加载训练好的模型并做推理 demo"""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if model_path is None:
        model_path = str(OUTPUT_DIR / "final")

    print(f"[推理] 加载: {model_path}")

    # 如果是 adapter 方式加载
    from peft import PeftModel

    base_model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = PeftModel.from_pretrained(base_model, model_path)
    model.eval()

    test_cases = [
        "甲状腺右叶见0.5×0.3cm低回声结节，边界清",
        "肝脏大小正常，右叶见0.8cm强回声，后方伴声影",
        "胆囊大小正常，壁不厚，腔内见1.2cm强回声，随体位移动",
        "子宫前位，肌层见1.5×1.2cm低回声，边界清",
    ]

    for text in test_cases:
        messages = [
            {"role": "system", "content": "你是一位超声科主任医师。根据口述超声描述，生成完整的结构化超声报告。"},
            {"role": "user", "content": text},
        ]
        input_text = tokenizer.apply_chat_template(messages, tokenize=False)
        inputs = tokenizer(input_text, return_tensors="pt").to("cuda")

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.1,
                top_p=0.9,
                repetition_penalty=1.05,
            )

        response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        print(f"\n{'='*50}")
        print(f"输入: {text}")
        print(f"{'='*50}")
        print(response)


# ─── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["train", "infer", "demo"], default="train")
    parser.add_argument("--model_path", type=str, default=None)
    parser.add_argument("--samples", type=int, default=50000)
    args = parser.parse_args()

    if args.samples:
        MAX_SAMPLES = args.samples

    if args.mode == "train":
        train()
    elif args.mode == "infer":
        inference_demo(args.model_path)
    elif args.mode == "demo":
        # 先训练一小批(2000条)做验证
        MAX_SAMPLES = 2000
        EPOCHS = 1
        model, tokenizer = train()
        inference_demo()
