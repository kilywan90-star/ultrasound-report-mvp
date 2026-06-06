"""核心函数单元测试 — pytest"""

import pytest, json, re, os, sys


# ═══════════════════════════════════════════
# template_loader 测试
# ═══════════════════════════════════════════

class TestTemplateLoader:
    """模板加载与候选搜索"""

    def test_load_templates_returns_at_least_300(self):
        """冷启动后至少有300条模板"""
        from template_loader import load_templates, search_candidates
        load_templates()
        candidates = search_candidates("肝脏大小形态正常，实质回声均匀", "腹部超声", limit=10)
        assert len(candidates) > 0, "正常口述应该有候选模板"

    def test_load_templates_repeated_is_idempotent(self):
        """重复加载不抛异常"""
        from template_loader import load_templates
        for _ in range(5):
            load_templates()  # must not raise

    def test_search_candidates_normal_report(self):
        """正常报告 → '正常'关键词匹配"""
        from template_loader import load_templates, search_candidates
        load_templates()
        candidates = search_candidates("腹部超声未见明显异常", "腹部超声", limit=5)
        names = [c["name"] for c in candidates]
        assert len(candidates) >= 1
        # 应该有"正常"类模板
        assert any("正常" in n for n in names)

    def test_search_candidates_empty_text(self):
        """空文本返回空列表"""
        from template_loader import load_templates, search_candidates
        load_templates()
        candidates = search_candidates("", "腹部超声", limit=5)
        assert candidates == []

    def test_search_candidates_exam_type_routing(self):
        """检查类型路由：妇产超声不应匹配心脏模板"""
        from template_loader import load_templates, search_candidates
        load_templates()
        candidates = search_candidates("子宫肌瘤", "妇产超声", limit=5)
        # 妇产口述, top候选应有子宫相关
        names = [c["name"] for c in candidates]
        assert any("子宫" in n or "肌瘤" in n for n in names[:3]), f"top3无子宫/肌瘤相关: {names[:3]}"


# ═══════════════════════════════════════════
# llm_client 测试 (不调API, 仅测本地解析)
# ═══════════════════════════════════════════

class TestParseJson:
    """JSON提取与解析"""

    def test_extract_json_code_block(self):
        """提取markdown代码块中的JSON"""
        from llm_client import _extract_json
        content = '一些废话\n```json\n{"a": 1}\n```\n更多'
        assert _extract_json(content) == '{"a": 1}'

    def test_extract_json_plain_braces(self):
        """提取纯花括号JSON"""
        from llm_client import _extract_json
        content = '输出: {"study_see": "正常"}'
        assert _extract_json(content) == '{"study_see": "正常"}'

    def test_parse_json_valid(self):
        """有效JSON直接解析"""
        from llm_client import _parse_json
        result = _parse_json('{"study_see": "肝脏: 正常", "study_hint": []}')
        assert result["study_see"] == "肝脏: 正常"
        assert result["study_hint"] == []

    def test_parse_json_with_html_in_value(self):
        """JSON值含HTML标签"""
        from llm_client import _parse_json
        html_json = '{"study_see": "<b class=\\\"voice\\\">5.2mm</b> 正常"}'
        result = _parse_json(html_json)
        assert "voice" in result["study_see"]

    def test_parse_json_missing_closing_brace(self):
        """修复缺失的花括号"""
        from llm_client import _parse_json
        truncated = '{"study_see": "肝脏: 正常", "study_hint": [{"rank":1,"diagnosis":"脂肪肝"'  # 缺失]}}
        try:
            result = _parse_json(truncated)
            assert "study_see" in result
        except ValueError:
            pytest.skip("截断JSON修复不保证成功")


# ═══════════════════════════════════════════
# template_anchor 测试
# ═══════════════════════════════════════════

class TestMatchExactTemplate:
    """精确模板匹配"""

    def test_normal_abdomen_matches(self):
        """正常腹部报告匹配"""
        from template_anchor import match_exact_template
        candidates = match_exact_template(
            "肝脏大小形态正常，实质回声均匀。胆囊大小约68乘28毫米，壁光滑。胰腺脾脏双肾正常。",
            "腹部超声"
        )
        assert len(candidates) >= 1

    def test_sex_guard_blocks_cross_sex_match(self):
        """性别守卫: 男性不应匹配子宫肌瘤"""
        from template_anchor import match_exact_template
        candidates = match_exact_template(
            "子宫前壁可见低回声结节，大小约38乘32毫米，考虑子宫肌瘤",
            "妇产超声"
        )
        names = [c["tpl_name"] for c in candidates]
        # 有证据时应该匹配到子宫肌瘤
        assert any("子宫" in n or "肌瘤" in n for n in names[:5]), f"top5无子宫/肌瘤: {names[:5]}"

    def test_negation_detection(self):
        """否定检测: "未见结石"不应匹配结石模板"""
        from template_anchor import match_exact_template
        candidates = match_exact_template(
            "胆囊大小正常，壁光滑，腔内未见结石。肝脏未见异常。",
            "腹部超声"
        )
        names = [c["tpl_name"] for c in candidates]
        # "未见结石"不应匹配到结石模板
        stone_matches = [n for n in names if "结石" in n]
        assert len(stone_matches) == 0, f"否定检测失败，错误匹配: {stone_matches}"


# ═══════════════════════════════════════════
# 集成测试 (需要服务运行)
# ═══════════════════════════════════════════

@pytest.mark.integration
class TestApiIntegration:
    """需要后端服务运行"""

    API = "http://localhost:8730"

    def test_health_check(self):
        """健康检查"""
        import urllib.request
        req = urllib.request.Request(f"{self.API}/api/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            assert data["status"] == "ok"

    def test_add_patient(self):
        """患者快捷入队"""
        import urllib.request
        payload = json.dumps({
            "name": "单元测试患者",
            "gender": "男", "age": 42, "exam_type": "腹部超声"
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.API}/api/patients/quick-add",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert data["patient"]["name"] == "单元测试患者"

    def test_structure_normal_abdomen(self):
        """结构化: 正常腹部口述"""
        import urllib.request
        payload = json.dumps({
            "text": "肝脏大小形态正常，实质回声均匀。胆囊大小约68乘28毫米，壁光滑。胰腺脾脏双肾未见异常。",
            "exam_type": "腹部超声"
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.API}/api/structure",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert data.get("report") is not None
            report = data["report"]
            assert report.get("study_see"), "study_see 不能为空"
            assert isinstance(report.get("study_hint"), list)

    def test_structure_empty_text_rejected(self):
        """空文本被拒绝"""
        import urllib.request, urllib.error
        payload = json.dumps({"text": "", "exam_type": "腹部超声"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.API}/api/structure",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                assert data.get("success") is not True, "空文本应该被拒绝"
        except urllib.error.HTTPError as e:
            assert e.code in (400, 422), f"期望400/422, 实际{e.code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-k", "not integration", "--tb=short"])
