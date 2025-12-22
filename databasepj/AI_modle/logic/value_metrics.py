# AI_modle/logic/value_metrics.py
from typing import Dict, Any, List, Optional

DIM_LABELS = [
    "風險承受度",
    "保障安全感需求",
    "家庭責任傾向",
    "健康風險敏感度",
    "長期規劃程度",
    "彈性與流動性偏好",
]

# 題目 -> 維度（你可按你的題目語意再微調）
Q_DIM_MAP = {
    "Q1": 0, "Q2": 1, "Q3": 2, "Q4": 3, "Q5": 4,
    "Q6": 5, "Q7": 0, "Q8": 1, "Q9": 2, "Q10": 3,
}

# A-E 分數
CHOICE_SCORE = {"A": 20, "B": 40, "C": 60, "D": 80, "E": 100}

# 1-5 分數（Likert）
LIKERT_SCORE = {"1": 20, "2": 40, "3": 60, "4": 80, "5": 100}

CN_LIKERT = [
    ("非常不同意", 20),
    ("不同意", 40),
    ("普通", 60),
    ("一般", 60),
    ("中立", 60),
    ("同意", 80),
    ("非常同意", 100),
]

CN_LEVEL = [
    ("低", 30),
    ("中", 60),
    ("高", 90),
]

def _pick_answer_value(raw: Any) -> str:
    """把 answers[Qx] 可能是 dict/str 的情況統一成字串"""
    if raw is None:
        return ""
    if isinstance(raw, dict):
        # 常見前端：{choice:"A. ..."} 或 {value:"..."} 或 {answer:"..."}
        raw = raw.get("choice") or raw.get("value") or raw.get("answer") or raw.get("text") or ""
    return str(raw).strip()

def _extract_score(v: Any) -> int:
    """
    盡可能從答案中抓到 0~100 分：
    支援：
      - "A. ..." / "B" / "E..."
      - "1"~"5" / "3. ..." / "5 分"
      - 中文：非常不同意/不同意/普通/同意/非常同意
      - 中文：低/中/高
    """
    s = _pick_answer_value(v)
    if not s:
        return 0

    u = s.upper()

    # 1) 先抓 A-E（允許前面有括號、空白）
    for ch in ["A", "B", "C", "D", "E"]:
        if u.startswith(ch) or u.startswith(f"{ch}.") or u.startswith(f"{ch}、") or u.startswith(f"({ch}") or u.startswith(f"【{ch}"):
            return CHOICE_SCORE[ch]

    # 也可能在中間出現「選 A」這種
    for ch in ["A", "B", "C", "D", "E"]:
        if f"選{ch}" in u or f"選項{ch}" in u:
            return CHOICE_SCORE[ch]

    # 2) 再抓 1-5（Likert）
    # 常見： "3" / "3. ..." / "3分" / "5 分"
    first = s[0]
    if first in LIKERT_SCORE:
        return LIKERT_SCORE[first]
    for d in ["1", "2", "3", "4", "5"]:
        if s.strip() == d or s.strip().startswith(d + ".") or (d + "分") in s or (d + " 分") in s:
            return LIKERT_SCORE[d]

    # 3) 中文 Likert（注意順序：非常不同意要先於不同意）
    for key, score in CN_LIKERT:
        if key in s:
            return score

    # 4) 低中高
    for key, score in CN_LEVEL:
        if key == s or key in s:
            return score

    return 0

def _normalize_keys(answers: Dict[str, Any]) -> Dict[str, Any]:
    """
    支援 Q1 / q1 / question1 / question_1 這種 key
    統一轉成 Q1~Q10
    """
    if not isinstance(answers, dict):
        return {}

    norm: Dict[str, Any] = {}

    for k, v in answers.items():
        ks = str(k).strip()
        if not ks:
            continue
        u = ks.upper()

        # 已經是 Qx
        if u.startswith("Q") and u[1:].isdigit():
            norm["Q" + u[1:]] = v
            continue

        # question / QUESTION_1 / question-1
        if "QUESTION" in u:
            digits = "".join([c for c in u if c.isdigit()])
            if digits:
                norm["Q" + digits] = v
                continue

        # 只有數字 key： "1"~"10"
        if u.isdigit():
            norm["Q" + u] = v
            continue

    # 若上面沒抓到，保底把原本的也放進去（避免全空）
    if not norm:
        norm = {str(k).upper(): v for k, v in answers.items()}

    return norm

def compute_value_metrics(answers: Dict[str, Any]) -> Dict[str, Any]:
    a = _normalize_keys(answers or {})

    q_labels: List[str] = []
    q_scores: List[int] = []
    answered = 0

    dim_sum = [0] * 6
    dim_cnt = [0] * 6

    for i in range(1, 11):
        qk = f"Q{i}"
        q_labels.append(qk)

        score = _extract_score(a.get(qk))
        if score > 0:
            answered += 1
        q_scores.append(score)

        dim_idx = Q_DIM_MAP.get(qk)
        if dim_idx is not None:
            dim_sum[dim_idx] += score
            dim_cnt[dim_idx] += 1

    dim_scores = []
    for k in range(6):
        dim_scores.append(round(dim_sum[k] / dim_cnt[k]) if dim_cnt[k] else 0)

    completion_ratio = answered / 10.0
    confidence = min(0.55 + completion_ratio * 0.4, 0.95)

    return {
        "completion": f"{answered}/10",
        "confidence": round(confidence, 2),
        "mode": "hybrid",  # Demo：規則量化 + AI 文案
        "charts": {
            "radar": {"labels": DIM_LABELS, "data": dim_scores},
            "bar": {"labels": q_labels, "data": q_scores},
        }
    }
