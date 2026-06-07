#!/usr/bin/env python3
"""
超声语音报告系统 — 综合回归测试
覆盖所有关键路径，确保重构不引入回归
用法:
    python tests/test_regression.py          # 跑全部
    python tests/test_regression.py -v       # 详细输出
    python tests/test_regression.py --skip-llm  # 跳过含LLM的测试
"""
import sys, os, time, json, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

PASS = 0
FAIL = 0
SKIP = 0
SKIP_LLM = "--skip-llm" in sys.argv
VERBOSE = "-v" in sys.argv


def test(name, func):
    global PASS, FAIL, SKIP
    try:
        func()
        PASS += 1
        if VERBOSE:
            print(f"  [OK] {name}")
    except Exception as e:
        FAIL += 1
        print(f"  [FAIL] {name}: {e}")


def assert_ok(resp, msg="status not 200"):
    assert resp.status_code == 200, f"{msg} (got {resp.status_code})"
    j = resp.json()
    assert j.get("success", True) is not False, f"api returned success=false: {j}"
    return j


# ═══════════════════════════════════════════
# 1. 健康检查
# ═══════════════════════════════════════════
def test_health():
    r = client.get("/api/health")
    j = assert_ok(r)
    assert "version" in j
    assert "v3.3" in j["version"]


def test_templates():
    r = client.get("/api/templates")
    assert_ok(r)


# ═══════════════════════════════════════════
# 2. 核心管线路由 /api/structure
# ═══════════════════════════════════════════
def test_structure_normal():
    """正常报告路径"""
    r = client.post("/api/structure", json={
        "text": "肝脏大小正常，回声均匀，未见明显异常",
        "exam_type": "腹部超声",
    })
    j = assert_ok(r)
    assert "report" in j
    assert j["method"] in ("converted_fill", "rule_fill", "template_fill", "llm_free")
    assert j["report"].get("recommendation", "") != "", "recommendation should not be empty"
    # 验证规则建议（非LLM）生效
    assert "定期" in j["report"].get("recommendation", ""), f"expected 定期 in recommendation, got '{j['report'].get('recommendation','')}'"


def test_structure_short_text():
    """过短文本应拒绝"""
    r = client.post("/api/structure", json={"text": "嗯"})
    assert r.status_code == 400


def test_structure_empty():
    """空文本应拒绝"""
    r = client.post("/api/structure", json={"text": ""})
    assert r.status_code == 422  # Pydantic validation


def test_structure_stone():
    """结石路径"""
    r = client.post("/api/structure", json={
        "text": "胆囊见一个1.2cm强回声团，伴声影，诊断为胆囊结石",
        "exam_type": "腹部超声",
    })
    j = assert_ok(r)
    assert j["report"].get("recommendation", "") != ""
    if not SKIP_LLM:
        assert j["report"].get("study_hint", []) is not None
        if j["report"].get("study_hint"):
            assert "结石" in j["report"]["study_hint"][0].get("diagnosis", "")


def test_structure_fetal():
    """胎儿路径"""
    r = client.post("/api/structure", json={
        "text": "胎儿头位，双顶径8.5cm，股骨长6.7cm，羊水正常，胎心140次/分",
        "exam_type": "产科超声",
    })
    j = assert_ok(r)


def test_structure_thyroid():
    """甲状腺路径"""
    r = client.post("/api/structure", json={
        "text": "甲状腺左叶见0.5×0.3cm低回声结节，边界清晰，二类",
        "exam_type": "甲状腺超声",
    })
    j = assert_ok(r)


def test_structure_multi_organ():
    """多器官路径"""
    r = client.post("/api/structure", json={
        "text": "肝脏大小正常，胆囊壁毛糙，胰腺正常，脾脏未见肿大",
        "exam_type": "腹部超声",
    })
    j = assert_ok(r)


# ═══════════════════════════════════════════
# 3. 固定模板
# ═══════════════════════════════════════════
def test_fixed_tags():
    r = client.get("/api/fixed-template/tags")
    assert_ok(r)


def test_fixed_defaults():
    r = client.get("/api/fixed-template/defaults")
    assert_ok(r)


def test_fixed_structure():
    r = client.post("/api/fixed-template/structure", json={
        "text": "肝脏大小正常，回声均匀",
        "fixed_template": "",
    })
    assert_ok(r)


# ═══════════════════════════════════════════
# 4. 模板搜索
# ═══════════════════════════════════════════
def test_template_search():
    r = client.get("/api/template/search?q=肝脏")
    j = assert_ok(r)
    assert len(j.get("templates", [])) > 0, "should match at least 1 template"


def test_template_search_by_module():
    r = client.get("/api/template/search?module=肝脏")
    j = assert_ok(r)


# ═══════════════════════════════════════════
# 5. 患者管理
# ═══════════════════════════════════════════
def test_patient_queue():
    r = client.get("/api/patients/queue")
    assert_ok(r)


def test_patient_quick_add():
    r = client.post("/api/patients/quick-add", json={
        "name": "回归测试患者",
        "gender": "女",
        "age": 35,
        "exam_type": "腹部超声",
    })
    j = assert_ok(r)
    assert "patient" in j


def test_patient_quick_add_invalid():
    """无效数据应拒绝"""
    r = client.post("/api/patients/quick-add", json={
        "name": "",
        "gender": "X",
        "age": 999,
        "exam_type": "",
    })
    assert r.status_code in (400, 422), f"expected 400/422, got {r.status_code}"


# ═══════════════════════════════════════════
# 6. 静态文件
# ═══════════════════════════════════════════
def test_static_index():
    r = client.get("/")
    assert r.status_code == 200
    assert "html" in r.headers.get("content-type", "")


def test_static_404():
    r = client.get("/nonexistent_file.html")
    assert r.status_code == 404


# ═══════════════════════════════════════════
# 7. 验证工具函数
# ═══════════════════════════════════════════
def test_sex_conflict():
    from validators.patient import detect_sex_conflict, mask_conflict_organs
    assert detect_sex_conflict("子宫大小正常", "男") is not None
    assert detect_sex_conflict("肝脏正常", "男") is None
    masked = mask_conflict_organs("子宫正常", "男")
    assert "[待确认]" in masked


def test_pregnancy_conflict():
    from validators.patient import detect_pregnancy_conflict
    assert detect_pregnancy_conflict("孕囊可见", "腹部超声", "男") is not None
    assert detect_pregnancy_conflict("肝脏正常", "腹部超声", "女") is None


# ═══════════════════════════════════════════
# 8. 推荐规则测试
# ═══════════════════════════════════════════
def test_recommendation_rules():
    """测试建议规则逻辑（私有辅助函数同步版）"""
    from routers.structure import _quick_recommendation
    r = _quick_recommendation("肝脏大小正常未见异常", "正常肝脏模板", {"study_see": "肝脏大小正常，回声均匀，未见明显异常"}, "腹部超声")
    assert r is not None and "定期" in r, f"expected 定期 in '{r}'"
    r = _quick_recommendation("胆囊结石", "胆囊结石", {"study_see": "胆囊见1.2cm强回声团"}, "腹部超声")
    assert r is not None and ("复查" in r or "注意" in r), f"expected 复查/注意 in '{r}'"
    r = _quick_recommendation("甲状腺结节", "甲状腺结节", {"study_see": "甲状腺左叶见0.5cm低回声结节"}, "腹部超声")
    assert r is not None and ("专科" in r or "复查" in r), f"expected 专科/复查 in '{r}'"

    # 混合场景：异常规则应优先于正常规则
    r = _quick_recommendation("胆囊结石", "胆囊结石", {"study_see": "胆囊大小正常，胆汁透声好，内见强回声团"}, "腹部超声")
    assert r is not None and "注意" in r, f"mixed: expected 注意 in '{r}'"


# ═══════════════════════════════════════════
# 9. 数据层测试（使用 db.py）
# ═══════════════════════════════════════════
def test_db_patient_ops():
    import db
    p = db.patient_add("回归DB测试", "女", 30, "腹部超声")
    assert p is not None
    assert p.get("id") is not None
    pid = p["id"]
    got = db.patient_get(pid)
    assert got is not None
    assert got["name"] == "回归DB测试"


# ═══════════════════════════════════════════
# 10. 知识库加载
# ═══════════════════════════════════════════
def test_knowledge_engine():
    from knowledge_engine import knowledge
    assert knowledge is not None
    assert len(knowledge.hotwords) > 0
    hw = knowledge.get_hotwords_for_asr()
    assert len(hw) > 0
    cd = knowledge.get_confusion_dict()
    assert len(cd) > 0


def test_loader_knowledge():
    from knowledge.loader import get_kb
    kb = get_kb()
    assert kb is not None
    assert len(kb.confusion_dict) > 0


# ═══════════════════════════════════════════
# 开始
# ═══════════════════════════════════════════
if __name__ == "__main__":
    print(f"{'='*60}")
    print(f"  超声报告系统 — 回归测试")
    print(f"  {'跳过LLM测试' if SKIP_LLM else '包含LLM测试'}")
    print(f"{'='*60}")
    print()

    start = time.time()

    # 按依赖顺序执行
    tests = [
        # 1. 基础设施
        ("健康检查", test_health),
        ("TEMPLATES列表", test_templates),
        # 2. 知识库
        ("知识引擎加载", test_knowledge_engine),
        ("Loader知识库", test_loader_knowledge),
        # 3. 数据层
        ("DB患者操作", test_db_patient_ops),
        # 4. 验证工具
        ("性别冲突检测", test_sex_conflict),
        ("妊娠冲突检测", test_pregnancy_conflict),
        # 5. 推荐规则
        ("推荐规则测试", test_recommendation_rules),
        # 6. 核心管线
        ("Structure-正常", test_structure_normal),
        ("Structure-短文本拒绝", test_structure_short_text),
        ("Structure-空文本拒绝", test_structure_empty),
        ("Structure-结石", test_structure_stone),
        ("Structure-胎儿", test_structure_fetal),
        ("Structure-甲状腺", test_structure_thyroid),
        ("Structure-多器官", test_structure_multi_organ),
        # 7. 固定模板
        ("Fixed-tags", test_fixed_tags),
        ("Fixed-defaults", test_fixed_defaults),
        ("Fixed-structure", test_fixed_structure),
        # 8. 模板搜索
        ("模板搜索关键词", test_template_search),
        ("模板搜索模块", test_template_search_by_module),
        # 9. 患者
        ("患者队列", test_patient_queue),
        ("患者快捷添加", test_patient_quick_add),
        ("患者添加无效数据", test_patient_quick_add_invalid),
        # 10. 静态文件
        ("静态文件 index.html", test_static_index),
        ("静态文件 404", test_static_404),
    ]

    for name, func in tests:
        if SKIP_LLM and "LLM" in name:
            SKIP += 1
            continue
        test(name, func)

    elapsed = time.time() - start
    print()
    print(f"{'='*60}")
    print(f"  完成: PASS={PASS} FAIL={FAIL} SKIP={SKIP}  ({elapsed:.1f}s)")
    print(f"{'='*60}")

    sys.exit(1 if FAIL > 0 else 0)
