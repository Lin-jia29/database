# logic/scoring.py
# 保單推薦：規則計分（平滑版）
# 特色：不做硬篩選，只產生 category/channel 的偏好與 top3

from typing import Dict, Any, List, Tuple

CATEGORY_NAMES = {
    "health_medical": "健康醫療",
    "cancer_medical": "癌症醫療",
    "long_term_care": "長期照顧",
    "life_protection": "壽險保障",
    "accident": "意外傷害",
    "travel": "旅行險",
    "investment": "投資型保險",
    "group": "團體保險",
    "savings_annuity": "還本/增額/年金",
    "health_management": "健康管理",
}

def _get_choice_text(answers: Dict[str, Any], qid: str) -> str:
    v = answers.get(qid)
    if isinstance(v, dict):
        return str(v.get("choice") or "").strip()
    if isinstance(v, str):
        return v.strip()
    return ""

def _get_multi_list(answers: Dict[str, Any], qid: str) -> List[str]:
    v = answers.get(qid)
    if isinstance(v, dict):
        arr = v.get("multi") or []
        return [str(x).strip() for x in arr if str(x).strip()]
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []

def _contains(s: str, *keys: str) -> bool:
    ss = (s or "")
    return any(k in ss for k in keys)

def compute_insurance_scoring(answers: Dict[str, Any]) -> Dict[str, Any]:
    # 初始化
    scores = {k: 0 for k in CATEGORY_NAMES.keys()}
    channels = {"online": 0, "bank": 0, "agent": 0}
    reasons: Dict[str, List[str]] = {k: [] for k in CATEGORY_NAMES.keys()}

    # ===== Q1 投保對象（影響：團體保險）=====
    q1 = _get_choice_text(answers, "Q1")
    if _contains(q1, "公司", "員工", "一群人") or _contains(q1, "E."):
        scores["group"] += 4
        reasons["group"].append("投保對象偏團體")
        channels["agent"] += 1  # 多半需要業務/團體方案

    # ===== Q4 家庭狀況（影響：壽險/長照）=====
    q4 = _get_choice_text(answers, "Q4")
    if _contains(q4, "已婚", "小孩"):
        scores["life_protection"] += 1
        reasons["life_protection"].append("家庭責任較高")
    if _contains(q4, "照顧", "長輩"):
        scores["long_term_care"] += 2
        reasons["long_term_care"].append("有長照情境")

    # ===== Q5 擔心事項（核心，多選）=====
    q5 = _get_multi_list(answers, "Q5")
    for opt in q5:
        if _contains(opt, "生病", "住院", "手術"):
            scores["health_medical"] += 2
            reasons["health_medical"].append("在意住院/手術支出")
            scores["cancer_medical"] += 1
        if _contains(opt, "癌症", "重大疾病"):
            scores["cancer_medical"] += 2
            reasons["cancer_medical"].append("擔心癌症/重疾")
            scores["health_medical"] += 1
        if _contains(opt, "失能", "長期照顧"):
            scores["long_term_care"] += 3
            reasons["long_term_care"].append("擔心失能/照護")
        if _contains(opt, "身故", "家人生活"):
            scores["life_protection"] += 3
            reasons["life_protection"].append("重視家庭保障")
        if _contains(opt, "車禍", "骨折", "意外"):
            scores["accident"] += 3
            reasons["accident"].append("意外風險較高")
        if _contains(opt, "退休", "教育", "穩穩存", "穩穩領"):
            scores["savings_annuity"] += 3
            reasons["savings_annuity"].append("偏好穩健儲蓄/年金")
        if _contains(opt, "投資", "漲跌", "報酬"):
            scores["investment"] += 3
            reasons["investment"].append("可接受投資波動")
            channels["bank"] += 1
        if _contains(opt, "健康檢查", "健康管理", "線上"):
            scores["health_management"] += 3
            reasons["health_management"].append("想要健康管理/服務")
        if _contains(opt, "老闆", "管理者", "員工"):
            scores["group"] += 3
            reasons["group"].append("有員工保障需求")

    # ===== Q6 保障時間（不做硬切，只加權）=====
    q6 = _get_choice_text(answers, "Q6")
    if _contains(q6, "短期", "1–3", "1-3"):
        scores["travel"] += 1
        scores["accident"] += 1
        reasons["travel"].append("短期需求可能有旅行/活動")
    elif _contains(q6, "10–20", "10-20", "中長期"):
        scores["life_protection"] += 1
        scores["savings_annuity"] += 1
    elif _contains(q6, "到老", "終身"):
        scores["long_term_care"] += 1
        scores["life_protection"] += 1

    # ===== Q7 風險承受度（影響：投資 vs 年金）=====
    q7 = _get_choice_text(answers, "Q7")
    if _contains(q7, "保守"):
        scores["savings_annuity"] += 2
        channels["bank"] += 1
    elif _contains(q7, "有漲有跌", "不要太刺激"):
        scores["investment"] += 1
        channels["bank"] += 1
    elif _contains(q7, "大波動", "成長"):
        scores["investment"] += 2

    # ===== Q8 通路偏好（只加分，不硬篩）=====
    q8 = _get_choice_text(answers, "Q8")
    if _contains(q8, "線上", "手機", "電腦") or _contains(q8, "A."):
        channels["online"] += 3
    elif _contains(q8, "銀行") or _contains(q8, "B."):
        channels["bank"] += 3
    elif _contains(q8, "業務", "面談") or _contains(q8, "C."):
        channels["agent"] += 2

    # ===== Q9 特殊情境（多選）=====
    q9 = _get_multi_list(answers, "Q9")
    for opt in q9:
        if _contains(opt, "海外", "旅遊", "出差"):
            scores["travel"] += 2
            reasons["travel"].append("有旅行/出差情境")
        if _contains(opt, "登山", "潛水", "環島", "活動"):
            scores["travel"] += 1
            scores["accident"] += 1
        if _contains(opt, "團體保險", "員工"):
            scores["group"] += 2
            reasons["group"].append("公司團保情境")

    # ===== 平滑：避免只靠單題決生死（小幅度補底）=====
    # 若使用者有選任何核心多選題（Q5/Q9），幫所有類別微量補底，避免極端偏科造成候選太窄
    if len(q5) > 0 or len(q9) > 0:
        for k in scores.keys():
            scores[k] += 0  # 保留結構，若你未來想加 0.5 可改 float

    # ===== 產出 top3（分數>0 優先；全 0 給預設）=====
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top = [it for it in sorted_items if it[1] > 0][:3]

    if len(top) == 0:
        # 預設：健康醫療、意外、壽險（最泛用）
        top = [("health_medical", 1), ("accident", 1), ("life_protection", 1)]

    top_categories = []
    for key, sc in top:
        rs = reasons.get(key) or []
        reason = rs[0] if len(rs) > 0 else "依問卷整體偏好推估"
        top_categories.append({
            "key": key,
            "name": CATEGORY_NAMES.get(key, key),
            "score": sc,
            "reason": reason[:30],
        })

    return {
        "scores": scores,
        "top_categories": top_categories,
        "channels": channels,
        "meta": {
            "version": "smooth_v1",
        }
    }
