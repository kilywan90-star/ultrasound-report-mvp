"""3维度核验: 意图识别准确性 / 输出-模板匹配度 / 补充内容完整性
基于 test_results_1000.csv (v1) 进行自动化核验
"""
import csv, re, json, sys
from collections import Counter, defaultdict

CSV = r"e:\qoder\ultrasound-report-mvp\backend\test_results_1000.csv"
rows = []
with open(CSV, "r", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows.append(r)

def strip_html(h):
    return re.sub(r'<[^>]+>', '', h or '').strip()

# ============================================================
# 领域知识
# ============================================================
# 检查类型 → 应匹配的器官/部位
EXAM_ORGANS = {
    "腹部超声": {"肝","胆囊","胆总管","胰腺","脾","肾","左肾","右肾"},
    "甲状腺超声": {"甲状腺"},
    "乳腺超声": {"乳腺","乳","腋窝","象限"},
    "前列腺超声": {"前列腺","精囊","膀胱"},
    "妇产超声": {"子宫","宫腔","卵巢","附件","盆腔","宫内"},
    "血管超声": {"颈动脉","椎动脉","锁骨下动脉","内中膜","管腔","斑块"},
    "心脏超声": {"心","瓣","室间隔","房","主动脉"},
}
# 检查类型 → 不应出现的其他类型专属器官
CROSS_ORGANS = {
    "腹部超声": {"甲状腺","乳腺","前列腺","精囊","子宫","卵巢","颈动脉","椎动脉","心室","心房"},
    "甲状腺超声": {"肝","胆囊","脾","肾","乳腺","前列腺","子宫","卵巢","颈动脉","心室"},
    "乳腺超声": {"肝","胆囊","脾","肾","甲状腺","前列腺","子宫","卵巢","颈动脉","心室"},
    "前列腺超声": {"肝","胆囊","脾","肾","甲状腺","乳腺","子宫","卵巢","颈动脉","心室"},
    "妇产超声": {"肝","胆囊","脾","肾","甲状腺","乳腺","前列腺","精囊","颈动脉","心室"},
    "血管超声": {"肝","胆囊","脾","肾","甲状腺","乳腺","前列腺","子宫","卵巢"},
    "心脏超声": {"肝","胆囊","脾","肾","甲状腺","乳腺","前列腺","子宫","卵巢","颈动脉","椎动脉"},
}
# 异常指示词
ABNORMAL_SIGNS = (
    "结节","钙化","增生","增大","稍大","囊肿","息肉","肌瘤","积液","积水",
    "结石","斑块","狭窄","炎","扩张","欠均匀","毛糙","增厚","衰减",
    "回声增强","回声减低","无回声","低回声","高回声","不规则","模糊",
    "占位","包块","反流","饱满","不均匀",
)
# 正常模板名关键词
NORMAL_TPL_KW = ("正常", "未见异常")

# ============================================================
# 维度1: 意图识别准确性
# ============================================================
print("=" * 70)
print("维度1: 意图识别(模板选择)准确性")
print("=" * 70)

intent_issues = []
intent_stats = Counter()

for r in rows:
    rid = r["序号"]
    exam = r["检查类型"]
    inp = r["输入文本"]
    tpl = r["意图模板"]
    method = r["处理方式"]
    warn = r["警告信息"]
    out = strip_html(r["最终输出"])

    issues = []

    # 1a. 模板与检查类型不匹配: 模板含其他检查类型的专属器官
    if tpl and "自由生成" not in tpl:
        cross = CROSS_ORGANS.get(exam, set())
        wrong_organs = [o for o in cross if o in tpl and len(o) >= 2]
        if wrong_organs:
            issues.append(f"模板含跨类型器官: {wrong_organs}")
            intent_stats["跨类型模板"] += 1

    # 1b. 异常输入匹配到正常模板(无ASR覆盖)
    has_abn = any(s in inp for s in ABNORMAL_SIGNS)
    is_normal_tpl = any(kw in tpl for kw in NORMAL_TPL_KW) if tpl else False
    asr_overridden = "ASR覆盖" in tpl or "ASR覆盖" in warn
    if has_abn and is_normal_tpl and not asr_overridden:
        issues.append(f"异常输入→正常模板'{tpl}'且无ASR覆盖")
        intent_stats["异常→正常模板"] += 1

    # 1c. 正常输入匹配到异常模板
    if not has_abn and tpl and "自由生成" not in tpl:
        abn_in_tpl = any(s in tpl for s in ABNORMAL_SIGNS)
        if abn_in_tpl:
            issues.append(f"正常输入→异常模板'{tpl}'")
            intent_stats["正常→异常模板"] += 1

    # 1d. 胎儿路径误判 (妇产超声但走了胎儿模板)
    if exam == "妇产超声" and method == "fetal_template":
        # 检查是否真的是胎儿测量 (有BPD/双顶径等)
        fetal_meas = ("双顶径", "BPD", "头围", "HC", "腹围", "AC", "股骨长", "FL")
        has_fetal_meas = any(s in inp for s in fetal_meas)
        if not has_fetal_meas:
            issues.append(f"妇产超声误入胎儿路径(无胎儿测量数据)")
            intent_stats["妇产→胎儿误判"] += 1

    # 1e. 自由生成时模板匹配分数为0 (可能模板库覆盖不足)
    if "自由生成" in (tpl or ""):
        reasoning = r.get("推理说明", "")
        if "最高分数0" in reasoning:
            intent_stats["零分回退"] += 1
        else:
            intent_stats["低分回退"] += 1

    if issues:
        intent_issues.append({"id": rid, "exam": exam, "input": inp[:100],
                              "template": tpl, "issues": issues, "output": out[:100]})

print(f"\n总测试: {len(rows)}")
print(f"意图识别问题: {len(intent_issues)}条")
print(f"\n问题细分:")
for k, v in intent_stats.most_common():
    print(f"  {k}: {v}")

# 自由生成统计
free_gen = sum(1 for r in rows if "自由生成" in (r["意图模板"] or ""))
print(f"\n模板匹配统计:")
print(f"  成功匹配模板: {len(rows) - free_gen} ({(len(rows)-free_gen)/len(rows)*100:.1f}%)")
print(f"  自由生成(无匹配): {free_gen} ({free_gen/len(rows)*100:.1f}%)")

print(f"\n--- 意图识别问题示例 (前15条) ---")
for item in intent_issues[:15]:
    print(f"  #{item['id']} [{item['exam']}]")
    print(f"    模板: {item['template']}")
    print(f"    问题: {'; '.join(item['issues'])}")
    print(f"    输入: {item['input']}...")
    print()


# ============================================================
# 维度2: 最终输出与模板内容匹配度
# ============================================================
print("\n" + "=" * 70)
print("维度2: 最终输出与模板内容匹配度")
print("=" * 70)

template_issues = []
tpl_issue_stats = Counter()

for r in rows:
    rid = r["序号"]
    exam = r["检查类型"]
    inp = r["输入文本"]
    tpl = r["意图模板"]
    out = strip_html(r["最终输出"])
    warn = r["警告信息"]
    method = r["处理方式"]

    issues = []

    # 2a. 输出含未填充占位符
    placeholders = re.findall(r'_{2,}|(?<!\w)x\s*(?:mm|cm)(?!\w)|未测', out, re.IGNORECASE)
    if placeholders:
        issues.append(f"含未填充占位符: {list(set(placeholders))[:3]}")
        tpl_issue_stats["占位符残留"] += 1

    # 2b. 输出与输入的器官不一致: 输出含输入未提及的其他类型器官
    cross = CROSS_ORGANS.get(exam, set())
    wrong_in_output = [o for o in cross if o in out and o not in inp and len(o) >= 2]
    # 排除正常排除描述(如"未见xxx")
    real_wrong = []
    for o in wrong_in_output:
        # 检查是否前面有"未见"/"未见明显"
        idx = out.find(o)
        prefix = out[max(0, idx-8):idx]
        if "未见" in prefix or "未探及" in prefix:
            continue
        real_wrong.append(o)
    if real_wrong:
        issues.append(f"输出含跨类型器官: {real_wrong[:3]}")
        tpl_issue_stats["跨类型器官输出"] += 1

    # 2c. 输出说正常但输入说异常(无ASR覆盖)
    normal_phrases = ("未见明显异常", "未见异常", "未见明显结节", "大小正常",
                      "回声均匀", "未见异常回声", "未见明显占位")
    abn_in_output = any(s in out for s in ABNORMAL_SIGNS)
    normal_in_output = sum(1 for p in normal_phrases if p in out)
    has_abn = any(s in inp for s in ABNORMAL_SIGNS)
    if has_abn and normal_in_output >= 3 and not abn_in_output:
        if "ASR覆盖" not in warn and "ASR覆盖" not in tpl:
            issues.append("输出说正常但输入说异常(无覆盖)")
            tpl_issue_stats["正常矛盾"] += 1

    # 2d. 输出重复内容
    sentences = re.split(r'[。；]', out)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 8]
    seen = set()
    dupes = []
    for s in sentences:
        s_norm = re.sub(r'\s+', '', s)
        if s_norm in seen:
            dupes.append(s[:30])
        seen.add(s_norm)
    if dupes and method != "fetal_template":
        issues.append(f"输出含重复: '{dupes[0]}'")
        tpl_issue_stats["重复内容"] += 1

    # 2e. 输出严重截断 (输出不到输入40%且输入有异常)
    inp_len = len(re.sub(r'[\s\W]', '', inp))
    out_len = len(re.sub(r'[\s\W]', '', out))
    if inp_len > 20 and out_len < inp_len * 0.35 and has_abn:
        issues.append(f"输出严重截断: 输入{inp_len}字→输出{out_len}字({out_len/inp_len:.0%})")
        tpl_issue_stats["内容截断"] += 1

    if issues:
        template_issues.append({"id": rid, "exam": exam, "input": inp[:100],
                                "template": tpl, "issues": issues, "output": out[:120]})

print(f"\n总测试: {len(rows)}")
print(f"输出-模板匹配问题: {len(template_issues)}条")
print(f"\n问题细分:")
for k, v in tpl_issue_stats.most_common():
    print(f"  {k}: {v}")

print(f"\n--- 输出-模板匹配问题示例 (前15条) ---")
for item in template_issues[:15]:
    print(f"  #{item['id']} [{item['exam']}]")
    print(f"    模板: {item['template']}")
    print(f"    问题: {'; '.join(item['issues'])}")
    print(f"    输入: {item['input']}...")
    print(f"    输出: {item['output']}...")
    print()


# ============================================================
# 维度3: 多出的有意义内容是否追加到最后
# ============================================================
print("\n" + "=" * 70)
print("维度3: 多出有意义内容是否追加到末尾(补充测量/补充内容)")
print("=" * 70)

appendix_issues = []
appendix_stats = Counter()

for r in rows:
    rid = r["序号"]
    exam = r["检查类型"]
    inp = r["输入文本"]
    out = strip_html(r["最终输出"])
    warn = r["警告信息"]

    issues = []

    # 提取输入中的所有数值
    inp_numbers = set(re.findall(r'\d+(?:\.\d+)?', inp))
    out_numbers = set(re.findall(r'\d+(?:\.\d+)?', out))
    missing_nums = inp_numbers - out_numbers
    # 过滤掉太小的数字(可能是模板自带的)
    missing_nums = {n for n in missing_nums if float(n) >= 0.3}

    # 3a. 输入有数值但输出丢失, 且无"补充测量"
    if missing_nums and "补充测量" not in out:
        issues.append(f"数值丢失: {sorted(missing_nums)[:5]} 且无补充")
        appendix_stats["数值丢失无补充"] += 1

    # 3b. 输入有异常发现但输出中该发现消失
    # 提取输入中的异常短语 (异常词+周边上下文)
    for sign in ABNORMAL_SIGNS:
        if sign not in inp:
            continue
        # 找到sign在input中的位置及上下文
        for m in re.finditer(re.escape(sign), inp):
            start = max(0, m.start() - 5)
            end = min(len(inp), m.end() + 10)
            context = inp[start:end]
            # 检查这个上下文是否出现在输出中
            # 放宽匹配: 只要核心异常词在输出中即可
            if sign not in out:
                # 检查是否是"未见+异常词"的模式(正常排除)
                sign_idx = inp.find(sign)
                prefix = inp[max(0, sign_idx-5):sign_idx]
                if "未见" in prefix:
                    break  # 输入本身就是正常排除描述
                issues.append(f"异常发现'{context}'在输出中消失")
                appendix_stats["异常发现消失"] += 1
                break  # 每个sign只报一次

    # 3c. 数值保全已触发(正面确认)
    if "补充测量" in out:
        appendix_stats["补充测量已触发"] += 1

    # 3d. 百分比格式丢失
    inp_pcts = re.findall(r'\d+(?:\.\d+)?\s*%', inp)
    for pct in inp_pcts:
        pct_num = re.findall(r'\d+(?:\.\d+)?', pct)
        if pct_num and pct_num[0] not in out:
            issues.append(f"百分比丢失: {pct}")
            appendix_stats["百分比丢失"] += 1

    if issues:
        appendix_issues.append({"id": rid, "exam": exam, "input": inp[:100],
                                "issues": issues, "output": out[:120], "warn": warn[:60]})

print(f"\n总测试: {len(rows)}")
print(f"补充内容问题: {len(appendix_issues)}条")
print(f"\n问题细分:")
for k, v in appendix_stats.most_common():
    print(f"  {k}: {v}")

print(f"\n--- 补充内容问题示例 (前15条) ---")
for item in appendix_issues[:15]:
    print(f"  #{item['id']} [{item['exam']}]")
    print(f"    问题: {'; '.join(item['issues'][:3])}")
    print(f"    输入: {item['input']}...")
    print(f"    输出: {item['output']}...")
    print(f"    警告: {item['warn']}")
    print()


# ============================================================
# 汇总报告
# ============================================================
print("\n" + "=" * 70)
print("三维核验汇总")
print("=" * 70)

total_issues_d1 = len(intent_issues)
total_issues_d2 = len(template_issues)
total_issues_d3 = len(appendix_issues)

# 计算无问题行数
all_issue_ids = set()
for item in intent_issues:
    all_issue_ids.add(("d1", item["id"]))
for item in template_issues:
    all_issue_ids.add(("d2", item["id"]))
for item in appendix_issues:
    all_issue_ids.add(("d3", item["id"]))

unique_bad_rows = set()
for dim, rid in all_issue_ids:
    unique_bad_rows.add(rid)

clean = len(rows) - len(unique_bad_rows)

print(f"""
总测试: {len(rows)}条

维度1 - 意图识别准确性:
  问题: {total_issues_d1}条 ({total_issues_d1/len(rows)*100:.1f}%)
  细分: {dict(intent_stats)}

维度2 - 输出与模板匹配度:
  问题: {total_issues_d2}条 ({total_issues_d2/len(rows)*100:.1f}%)
  细分: {dict(tpl_issue_stats)}

维度3 - 补充内容完整性:
  问题: {total_issues_d3}条 ({total_issues_d3/len(rows)*100:.1f}%)
  细分: {dict(appendix_stats)}

综合:
  至少1个维度有问题: {len(unique_bad_rows)}条 ({len(unique_bad_rows)/len(rows)*100:.1f}%)
  三维全部通过: {clean}条 ({clean/len(rows)*100:.1f}%)
""")

# 保存核验报告
report = {
    "dimension1_intent": {
        "total_issues": total_issues_d1,
        "stats": dict(intent_stats),
        "cases": [{"id": i["id"], "exam": i["exam"], "input": i["input"],
                    "template": i["template"], "issues": i["issues"]} for i in intent_issues[:50]],
    },
    "dimension2_template_match": {
        "total_issues": total_issues_d2,
        "stats": dict(tpl_issue_stats),
        "cases": [{"id": i["id"], "exam": i["exam"], "input": i["input"],
                    "template": i["template"], "issues": i["issues"]} for i in template_issues[:50]],
    },
    "dimension3_appendix": {
        "total_issues": total_issues_d3,
        "stats": dict(appendix_stats),
        "cases": [{"id": i["id"], "exam": i["exam"], "input": i["input"],
                    "issues": i["issues"]} for i in appendix_issues[:50]],
    },
    "summary": {
        "total": len(rows),
        "clean": clean,
        "dirty": len(unique_bad_rows),
        "clean_pct": f"{clean/len(rows)*100:.1f}%",
    }
}
path = CSV.replace("test_results_1000.csv", "verification_3dim.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f"详细报告已保存: {path}")
