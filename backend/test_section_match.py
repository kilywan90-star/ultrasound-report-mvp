#!/usr/bin/env python3
"""Test script for section match engine with report output"""
import sys, json, re
sys.path.insert(0, r'E:\claude\ultrasound-report-mvp\backend')
sys.stdout.reconfigure(encoding='utf-8')
from template_anchor import anchored_structure

test_cases = [
    ("腹部完整正常", "肝脏形态规则大小正常实质回声分布均匀肝内管系尚清胆囊大小正常壁光滑透声可胆囊内未见明显异常回声胆总管上段内径正常脾厚正常胰头胰体正常双肾形态规则大小正常实质回声分布均匀CDFI所检脏器未见明显异常血流信号", "腹部超声"),
    ("前列腺钙化灶", "前列腺形态饱满大小约42x30mm实质回声欠均匀内可见强光斑", "泌尿前列腺"),
    ("甲状腺结节", "甲状腺双侧叶切面形态规则大小正常表面光滑实质回声分布均匀内未见明显结节及占位回声CDFI甲状腺结节内未见明显血流信号双侧颈部未见明显肿大淋巴结回声", "甲状腺超声"),
    ("心脏E<A返流", "CDFI E小于A房室间隔未见过隔血流各瓣膜口未见明显返流血彩", "心脏超声"),
    ("胆囊多发息肉", "胆囊大小形态正常壁欠光滑内见多个附壁稍高回声结节无声影不随体位改变而移动较大约8x6mm胆总管上段内径正常", "腹部超声"),
    ("产科LLM回落", "孕妇停经38周双顶径92mm股骨长71mm胎盘后壁羊水指数108mm", "妇产超声"),
]

print("=" * 70)
print("Template Engine Verification Report")
print("=" * 70)
all_ok = True
for label, text, exam in test_cases:
    try:
        r = anchored_structure(text, exam)
        method = r['method']
        ms = r['elapsed_ms']
        confidence = r.get('confidence', 0)
        tpl_id = r.get('template_used', 'N/A')
        see = r['report'].get('study_see', '')
        lines = see.count('\n') + 1 if see else 0
        print(f"\n[{label}]")
        print(f"  Method:     {method}")
        print(f"  Time:       {ms}ms")
        print(f"  Template:   {tpl_id}")
        print(f"  Confidence: {confidence}")
        print(f"  Paragraphs: {lines}")
        if see:
            first_line = see.split('\n')[0] if '\n' in see else see[:100]
            print(f"  First line: {first_line[:100]}")
    except Exception as e:
        print(f"\n[{label}] ERROR: {e}")
        all_ok = False

print(f"\n{'='*70}")
print(f"All passed: {all_ok}")
