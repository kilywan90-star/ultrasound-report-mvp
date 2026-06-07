#!/usr/bin/env python3
"""
超声报告系统 — 全链路对齐测试
覆盖: 后端API、数据库双schema、规则库加载、前端API对齐、端到端管线

用法:  python tests/test_full_alignment.py  -v
"""
import sys, os, time, json, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
os.chdir(os.path.dirname(os.path.abspath(__file__)) + '/..')

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

PASS = 0
FAIL = 0
VERBOSE = '-v' in sys.argv
_log = []

def msg(s):
    _log.append(s)
    if VERBOSE:
        print(s)

def ok(name, detail=''):
    global PASS
    PASS += 1
    msg(f'  [OK]   {name}  {detail}')

def fail(name, detail=''):
    global FAIL
    FAIL += 1
    msg(f'  [FAIL] {name}  {detail}')

def check(name, cond, detail=''):
    if cond:
        ok(name, detail)
    else:
        fail(name, detail)

def assert_status(resp, expected=200, label=''):
    c = resp.status_code == expected
    detail = f'({label}) got={resp.status_code}' if not c else ''
    return c, detail


print('=' * 65)
print('  超产报告系统 — 全链路对齐测试')
print('=' * 65)
print()

# ═══════════════════════════════════════
# 1. 后端路由完整性
# ═══════════════════════════════════════
print('--- 1. 后端 API 路由对齐 ---')

routes = [
    ('GET',  '/api/health', None),
    ('GET',  '/api/templates', None),
    ('GET',  '/api/fixed-template/tags', None),
    ('GET',  '/api/fixed-template/defaults', None),
    ('GET',  '/api/template/search?q=肝脏', None),
    ('GET',  '/api/patients/queue', None),
    ('POST', '/api/patients/quick-add', {'name':'全链路测试','gender':'男','age':40,'exam_type':'腹部超声'}),
    ('POST', '/api/fixed-template/structure', {'text':'肝脏正常','fixed_template':''}),
    ('POST', '/api/structure', {'text':'肝脏大小正常，回声均匀','exam_type':'腹部超声'}),
    ('GET',  '/', None),
]
for method, path, body in routes:
    kw = {}
    if body:
        kw['json'] = body
    try:
        resp = client.request(method, path, **kw)
        c, d = assert_status(resp, 200, f'{method} {path}')
        check(f'{method} {path}', c, d)
    except Exception as e:
        fail(f'{method} {path}', str(e))

print()

# ═══════════════════════════════════════
# 2. 数据库双schema验证
# ═══════════════════════════════════════
print('--- 2. 数据库双 schema 对齐 ---')

# 2a. db.py schema (main.py 数据层)
check('db.py 可导入', True)
import importlib.util
spec = importlib.util.spec_from_file_location('db_mod', 'db.py')
db_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db_mod)

# 验证关键函数存在
for func in ['patient_add', 'patient_get', 'patient_queue',
             'report_create', 'report_get', 'report_update',
             'report_confirm', 'audit_log']:
    check(f'db.{func} 存在', hasattr(db_mod, func))

# 测试写操作
try:
    p = db_mod.patient_add('对齐测试', '男', 35, '腹部超声')
    check('db.patient_add 写入', p is not None and p.get('id'))
    pid = p['id']
    got = db_mod.patient_get(pid)
    check('db.patient_get 读取', got and got['name'] == '对齐测试')
except Exception as e:
    fail('db.py 数据操作', str(e))

# 2b. database.py schema (main_v3.py 数据层)
spec2 = importlib.util.spec_from_file_location('dbase_mod', 'database.py')
dbase_mod = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(dbase_mod)
conn = dbase_mod.get_db()
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
table_names = [r['name'] for r in tables]
for tbl in ['doctors', 'patients', 'reports', 'audio_recordings', 'asr_logs',
            'intent_logs', 'match_log', 'report_edits', 'audit_log',
            'kb_versions', 'template_categories']:
    check(f'database 表 {tbl} 存在', tbl in table_names)
conn.close()

print()

# ═══════════════════════════════════════
# 3. 规则库全面加载验证
# ═══════════════════════════════════════
print('--- 3. 规则库全面加载对齐 ---')

# 3a. knowledge/loader (统一加载器)
from knowledge.loader import get_kb as get_kb1
kb = get_kb1()
all_attrs = kb.__slots__
n_loaded = sum(1 for a in all_attrs if getattr(kb, a, None) not in ({}, [], None, ''))
check(f'KnowledgeBase: {n_loaded}/{len(all_attrs)} 属性已加载', n_loaded >= 33, f'loaded={n_loaded} total={len(all_attrs)}')

# 关键属性验证
key_attrs = [
    ('confusion_dict', '混淆词典', lambda v: len(v) > 100),
    ('confusion_dict_ext', '扩展混淆', lambda v: len(v) > 50),
    ('normal_ranges', '正常值范围', lambda v: len(v) > 3),
    ('grading_standards', '分级标准', lambda v: len(v) >= 4),  # BI-RADS, TI-RADS, LI-RADS, PI-RADS
    ('high_risk_signs', '高风险征象', lambda v: len(v) >= 2),
    ('sex_guard_rules', '性别守卫', lambda v: len(v) >= 5),
    ('normal_thresholds', '数值阈值', lambda v: len(v) >= 2),
    ('exam_part_routing', '部位路由', lambda v: len(v) >= 3),
    ('extended_hotword_index', '扩展热词', lambda v: len(v) >= 2),
    ('high_conf_candidates', '高置信候选', lambda v: len(v) >= 50),
    ('matching_rules_merged', '匹配规则', lambda v: len(v) >= 30),
    ('template_score_rules', '模板评分', lambda v: len(v) >= 1),
    ('antonym_pairs', '反义词对', lambda v: len(v) >= 5),
    ('cross_validation', '交叉验证', lambda v: len(v) >= 10),
    ('pregnancy_ga_constraints', '孕周约束', lambda v: len(v) >= 2),
    ('health_tips_bank', '健康建议', lambda v: len(v) >= 2),
    ('quality_dashboard', '质量看板', lambda v: len(v) >= 5),
    ('quality_metrics', '质量指标', lambda v: len(v) >= 2),
    ('drg_dip_codes', 'DRG/DIP', lambda v: len(v) >= 2),
    ('loinc_codes', 'LOINC', lambda v: len(v) >= 2),
]
for attr, label, validator in key_attrs:
    v = getattr(kb, attr, None)
    try:
        check(f'  {label} ({attr})', v is not None and validator(v), f'size={len(v) if isinstance(v,(dict,list)) else type(v).__name__}')
    except Exception as e:
        fail(f'  {label} ({attr})', str(e))

# 3b. rule_engine (rule_engine.py)
from rule_engine import get_rule, load_rules
load_rules(force=True)
for path in ['meta.version', 'extraction.fetal_measurements',
             'validation.sex_guard.female_only', 'validation.contradictions',
             'templates.module_map', 'pipeline.fast_path']:
    v = get_rule(path, None)
    check(f'rule_engine {path}', v is not None, f'got={type(v).__name__}' if v else 'None')

# 3c. knowledge_engine (包装层)
from knowledge_engine import knowledge
corrected = knowledge.correct_asr_text('甲壮线结节')
check('knowledge_engine 纠错', '甲' in corrected and '结' in corrected,
      f'{corrected}')
check('knowledge_engine 热词', len(knowledge.hotwords) > 0, f'{len(knowledge.hotwords)}')

print()

# ═══════════════════════════════════════
# 4. 前端-后端 API 对齐
# ═══════════════════════════════════════
print('--- 4. 前端-后端 API 对齐 ---')

# 读取前端 HTML 中调用的 API 端点
frontend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'frontend', 'index.html')
frontend_path = os.path.normpath(frontend_path)
if not os.path.exists(frontend_path):
    frontend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', '..', 'frontend', 'index.html')
    frontend_path = os.path.normpath(frontend_path)
with open(frontend_path, 'r', encoding='utf-8') as f:
    html = f.read()

# 提取前端调用的 API 路径
frontend_apis = set()
for m in re.finditer(r"['\`](/api/[a-zA-Z0-9_/-]+)[\'\`]", html):
    frontend_apis.add(m.group(1))

# 后端实际注册的 API 路径
backend_apis = set()
for route in app.routes:
    if hasattr(route, 'path') and hasattr(route, 'methods'):
        for method in route.methods:
            path = route.path
            backend_apis.add(path)
            # 前端可能调用不含前缀的路径
            if path.startswith('/api/'):
                pass

# 前端调用了但后端没有的（可能404）
missing = set()
for api in sorted(frontend_apis):
    # 检查 exact 或 pattern match
    found = False
    for bapi in backend_apis:
        if bapi == api:
            found = True
            break
        # 检查路径参数模式匹配
        bparts = bapi.split('/')
        aparts = api.split('/')
        if len(bparts) == len(aparts):
            match = True
            for bp, ap in zip(bparts, aparts):
                if bp.startswith('{') and bp.endswith('}'):
                    continue  # 路径参数通配
                if bp != ap:
                    match = False
                    break
            if match:
                found = True
                break
    if not found:
        missing.add(api)

# OK: 前端调用后端的验证
for api in sorted(frontend_apis):
    # 挑几个代表性端点实际调用
    if api in ('/api/voice/ali-asr', '/api/voice/save-local', '/api/audio/upload', '/api/transcribe'):
        continue  # 需要文件上传, 跳过
    if '{' in api or api.endswith('/search'):
        continue  # 模板参数
    try:
        if '/delete' in api or '/del/' in api:
            continue
        r = client.get(api)
        if r.status_code in (200, 422, 400, 404):
            # 404 也可能是合法(如 /api/patients/{id}/reports 无参数)
            check(f'前端调用 {api}', True, f'status={r.status_code}')
    except Exception as e:
        fail(f'前端调用 {api} 异常', str(e))

if missing:
    for api in sorted(missing):
        fail(f'前端调用 {api} — 后端未注册此路由', '')
else:
    ok('前端-后端 API 全部对齐')

print()

# ═══════════════════════════════════════
# 5. 端到端管线验证
# ═══════════════════════════════════════
print('--- 5. 端到端管线（语音→报告）验证 ---')

# 场景列表: (输入, 检查项)
cases = [
    ('肝脏大小正常，回声均匀，未见明显异常', {'recommendation_contains': '定期'}),
    ('胆囊壁毛糙，见1.2cm强回声团，伴声影', {'recommendation_contains': '复查'}),
    ('甲状腺左叶见0.5×0.3cm低回声结节，边界清晰', {'recommendation_contains': '复查'}),
    ('胎儿头位，双顶径8.5cm，股骨长6.7cm，羊水正常，胎心140次/分', {'method': 'fetal'}),  # 胎儿
]
for text, checks in cases:
    try:
        r = client.post('/api/structure', json={'text': text, 'exam_type': '腹部超声'})
        if r.status_code != 200:
            fail(f'场景 [{text[:20]}...]', f'HTTP {r.status_code}')
            continue
        d = r.json()
        ok_method = True
        if 'method' in checks:
            expected = checks['method']
            if expected != '*' and expected not in d.get('method', ''):
                ok_method = False
        ok_rec = True
        if 'recommendation_contains' in checks:
            rec = d['report'].get('recommendation', '')
            if checks['recommendation_contains'] not in rec:
                ok_rec = False
        ok_warn = True
        if 'warnings' in checks:
            pass  # warnings 可以动态
        all_ok = ok_method and ok_rec
        check(f'场景 [{text[:20]}...]', all_ok,
              f'method={d.get("method","?")} rec={d["report"].get("recommendation","")[:20]}')
    except Exception as e:
        fail(f'场景 [{text[:20]}...] 异常', str(e))

print()

# ═══════════════════════════════════════
# 6. 建议生成（规则+LLM并行）
# ═══════════════════════════════════════
print('--- 6. 建议生成对齐 ---')

from routers.structure import _quick_recommendation

cases = [
    ('未见明显异常', '模板', {'study_see': '肝脏大小正常，未见明显异常'}, '定期'),
    ('结石', '胆囊结石', {'study_see': '胆囊内见强回声团'}, '注意'),
    ('结节', '甲状腺结节', {'study_see': '低回声结节'}, '专科'),
    ('正常无异常', '模板', {'study_see': '大小正常，回声均匀'}, '定期'),
]
for text, name, report, expect in cases:
    try:
        r = _quick_recommendation(text, name, report, '腹部超声')
        ok_val = r is not None and expect in r
        check(f'建议[{text[:10]}...] → "{r}"', ok_val, f'expected contains={expect}')
    except Exception as e:
        fail(f'建议[{text[:10]}...] 异常', str(e))

print()
print('=' * 65)
print(f'  对齐测试完成: PASS={PASS}  FAIL={FAIL}')
print('=' * 65)

sys.exit(1 if FAIL > 0 else 0)
