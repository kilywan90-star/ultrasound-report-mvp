"""
医生偏好学习引擎 — 根据历史选择调整模板排序

核心逻辑：
  1. 从 doctor_preferences 表加载该医生的偏好
  2. 对候选模板列表做偏好加权重排序
  3. 根据调整后 Top1 的置信度决定自动填充或弹窗
"""

import logging
from db import doctor_preferences_get

logger = logging.getLogger(__name__)

# 偏好加权系数
PREFERENCE_BOOST = 0.15       # 医生选过一次的模板 +0.15
PREFERENCE_REPEAT_BOOST = 0.05  # 每多选一次再多加 0.05 (上限 0.25)
PREFERENCE_CAP = 0.40         # 偏好加权上限

# 置信度阈值
CONFIDENCE_AUTO = 0.90        # >= 90% 直接自动填充
CONFIDENCE_SHOW_CANDIDATES = 0.55  # >= 55% 展示候选模板让医生选
# < 50% 表示匹配不充分，提示医生继续口述


def rank_candidates(
    candidates: list[dict],
    doctor_id: int,
    doctor_name: str = "",
    site: str = None,
) -> dict:
    """
    对候选模板做偏好加权重排序

    参数:
        candidates: 原始候选列表 [{'template_id','template_name','score','site','description',...}]
        doctor_id: 医生ID
        doctor_name: 医生名
        site: 器官部位

    返回:
        {
            'candidates': [...],        # 重排序后的候选
            'top_conf': float,          # Top1 加权后置信度
            'auto_fill': bool,          # 是否自动填充
            'show_selection': bool,     # 是否展示候选让医生选
            'needs_more': bool,         # 是否匹配不足需继续口述
            'boosted_by_preference': bool,  # 是否因为偏好调整了排序
        }
    """
    if not candidates:
        return {
            'candidates': [],
            'top_conf': 0,
            'auto_fill': False,
            'show_selection': False,
            'needs_more': True,
            'boosted_by_preference': False,
        }

    # 1. 获取医生偏好
    prefs = doctor_preferences_get(doctor_id, site)
    pref_map = {p['template_id']: p for p in prefs}

    boosted = False

    # 2. 对每个候选做偏好加权
    scored = []
    for c in candidates:
        raw_score = c.get('score', 0) or 0
        pref = pref_map.get(c.get('template_id', ''))
        boost = 0
        if pref:
            count = pref.get('chosen_count', 1)
            boost = PREFERENCE_BOOST + min(PREFERENCE_REPEAT_BOOST * (count - 1), PREFERENCE_CAP - PREFERENCE_BOOST)
            boost = min(boost, PREFERENCE_CAP)
            boosted = True
        adjusted = min(raw_score + boost, 1.0)
        scored.append((adjusted, raw_score, boost, c))

    # 3. 按加权分降序排列
    scored.sort(key=lambda x: -x[0])

    # 4. 重新拼装 candidates
    reordered = []
    for adjusted, raw, boost, orig in scored:
        entry = dict(orig)
        entry['adjusted_score'] = round(adjusted, 4)
        entry['raw_score'] = entry.get('score', 0)
        entry['score'] = round(adjusted, 4)
        entry['preference_boost'] = round(boost, 4)
        reordered.append(entry)

    top_conf = reordered[0]['score'] if reordered else 0

    return {
        'candidates': reordered,
        'top_conf': top_conf,
        'auto_fill': top_conf >= CONFIDENCE_AUTO,
        'show_selection': CONFIDENCE_SHOW_CANDIDATES <= top_conf < CONFIDENCE_AUTO,
        'needs_more': top_conf < CONFIDENCE_SHOW_CANDIDATES,
        'boosted_by_preference': boosted,
    }
