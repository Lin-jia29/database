import json
import requests
import json5
import traceback
from typing import Any, Dict, List, Optional, Tuple
from flask import Flask, render_template, request, jsonify, abort
from logic.value_metrics import compute_value_metrics



# === 接上 scoring + DB repository ===
from logic.scoring import compute_insurance_scoring
from database.product_repository import (
    recommend_top3_products,
    attach_riders_to_mains,
    get_product_by_id,
    get_db_connection,
)

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False


@app.errorhandler(Exception)
def _handle_all_errors(e):
    traceback.print_exc()
    if request.path == "/submit":
        return jsonify({"status": "error", "message": str(e)}), 500
    return f"Server Error: {e}", 500


USER_DATA_STORE = {}
AI_RESULT_STORE = {}

LLAMA_MODEL = "llama3:8b-instruct-q4_k_m"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

SYSTEM_PROMPT_VALUES = """你是一位專業的保險顧問 AI，必須使用「繁體中文」回答。
請根據提供的用戶數據，執行專業的個人價值觀分析。

嚴格規則：
- 只能輸出「純 JSON」，不得有 Markdown、不得有多餘文字
- JSON 內所有文字必須是「繁體中文」，禁止英文（包含 Type / Reason / insurance_advice）
- Reason 請寫得更完整、更可用於 Demo（約 150~220 字），要有「推導邏輯」：觀察 → 推論 → 建議方向
- insurance_advice 請給 5 點，語氣專業、可直接拿來講 Demo

輸出格式如下：
{
  "status": "success",
  "value_profile": {
    "Type": "人格/價值觀類型（繁體中文）",
    "Reason": "分析總結（繁體中文，150~220字）"
  },
  "insurance_advice": [
    "建議1（繁體中文）",
    "建議2（繁體中文）",
    "建議3（繁體中文）",
    "建議4（繁體中文）",
    "建議5（繁體中文）"
  ]
}
"""


SYSTEM_PROMPT_INSURANCE = """你是一位專業的保險顧問 AI。你會收到：
1) 用戶問卷答案（含選項與自由文字）
2) 系統規則計分結果（Top 類別與原因）
3) 從資料庫篩選出的 3 個推薦商品（含名稱/簡述/特色/示例保費等）

請你輸出「繁體中文」的顧問解讀，並務必只輸出純 JSON（不要 Markdown）。
格式如下:
{
  "status": "success",
  "person_summary": "這是什麼樣的人（繁體中文，120字以內）",
  "top_categories": [
    {"name": "類別1", "reason": "原因（30字內）"},
    {"name": "類別2", "reason": "原因（30字內）"},
    {"name": "類別3", "reason": "原因（30字內）"}
  ],
  "next_step": [
    "下一步建議1",
    "下一步建議2",
    "下一步建議3"
  ],
  "product_advice": [
    "針對推薦商品的購買/比較重點（3點，繁體中文）"
  ]
}
"""


def call_ollama_api(system_prompt: str, user_input_json: str) -> str:
    payload = {
        "model": LLAMA_MODEL,
        "prompt": user_input_json,
        "system": system_prompt,
        "stream": False,
        "format": "json",
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        full = (data.get("response") or "").strip()

        s = full
        if "```json" in s:
            s = s.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in s:
            s = s.split("```", 1)[1].split("```", 1)[0]
        s = s.strip()

        if not s.startswith("{"):
            start = s.find("{")
            end = s.rfind("}")
            if start != -1 and end != -1 and end > start:
                s = s[start : end + 1].strip()
        return s
    except Exception as e:
        raise Exception(f"AI 服務連線失敗：{e}")


def _safe_parse_json(ai_text: str) -> dict:
    try:
        return json5.loads(ai_text)
    except Exception:
        pass
    try:
        s = (ai_text or "").strip()
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json5.loads(s[start : end + 1])
    except Exception:
        pass
    return {"status": "error", "message": "AI 回傳不是合法 JSON", "raw": (ai_text or "")[:1200]}


def _age_group_to_age(age_choice: str):
    if not age_choice:
        return None
    s = str(age_choice)
    if "0–20" in s or "0-20" in s:
        return 18
    if "21–30" in s or "21-30" in s:
        return 26
    if "31–45" in s or "31-45" in s:
        return 38
    if "46–60" in s or "46-60" in s:
        return 53
    if "61" in s:
        return 65
    return None


def _infer_quiz_id_from_answers(explicit_quiz_id: str, answers) -> str:
    q = (explicit_quiz_id or "").lower().strip()
    if not isinstance(answers, dict):
        return q if q in ("insurance", "values") else "values"

    keys = set(str(k) for k in answers.keys())
    looks_like_insurance = any(k.startswith("Q") for k in keys) or ("Q1" in keys) or ("Q2" in keys)
    looks_like_values = any(k.startswith("q") for k in keys) or ("age" in keys) or ("gender" in keys) or ("job" in keys)

    if looks_like_insurance and not looks_like_values:
        return "insurance"
    if looks_like_values and not looks_like_insurance:
        return "values"
    return q if q in ("insurance", "values") else "values"


# =========================
# Values：量化拆維度 + 圖表資料
# =========================
def _choice_to_1_5(v: Any) -> Optional[int]:
    """
    把各種 answers 格式盡量轉成 1~5 分：
    - 數字/字串數字：1~5
    - A/B/C/D/E：1~5
    - dict：優先 score/value，其次 choice（含 A. / B.）
    """
    if v is None:
        return None

    if isinstance(v, dict):
        for key in ("score", "value", "val"):
            if key in v:
                return _choice_to_1_5(v.get(key))
        if "choice" in v:
            return _choice_to_1_5(v.get("choice"))
        return None

    if isinstance(v, (int, float)):
        x = int(round(float(v)))
        if 1 <= x <= 5:
            return x
        return None

    s = str(v).strip()
    if s.isdigit():
        x = int(s)
        if 1 <= x <= 5:
            return x
        return None

    # "A." / "A" / "B ..." / "C、"
    up = s.upper()
    if len(up) >= 1 and up[0] in ("A", "B", "C", "D", "E"):
        mp = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}
        return mp.get(up[0])

    return None


def _collect_q_scores(answers: Dict[str, Any], n: int = 10) -> Tuple[List[Optional[int]], int]:
    scores: List[Optional[int]] = []
    answered = 0
    for i in range(1, n + 1):
        v = answers.get(f"q{i}")
        sc = _choice_to_1_5(v)
        scores.append(sc)
        if sc is not None:
            answered += 1
    return scores, answered


def _to_0_100(x_1_5: Optional[int]) -> Optional[int]:
    if x_1_5 is None:
        return None
    # 1->10, 5->90（留點邊界讓圖好看）
    return int(round(10 + (x_1_5 - 1) * 20))


def _avg(vals: List[Optional[int]]) -> Optional[int]:
    xs = [v for v in vals if v is not None]
    if not xs:
        return None
    return int(round(sum(xs) / len(xs)))


def _build_value_metrics(answers: Dict[str, Any]) -> Dict[str, Any]:
    q, answered = _collect_q_scores(answers, 10)
    q100 = [_to_0_100(x) for x in q]

    # 維度拆分（你可以之後按實際問卷語意微調映射）
    # 假設：q1~q10 都是 1~5 越高越偏向「該特徵更強」
    dims = {
        "風險承受度": _avg([q100[2], q100[6]]),          # q3, q7
        "保障安全感需求": _avg([q100[0], q100[4]]),       # q1, q5
        "家庭責任導向": _avg([q100[1], q100[7]]),         # q2, q8
        "健康風險敏感度": _avg([q100[3], q100[8]]),       # q4, q9
        "長期規劃程度": _avg([q100[5], q100[9]]),         # q6, q10
        "彈性與流動性偏好": _avg([q100[6], q100[9]]),     # q7, q10（偏彈性）
    }

    # profile 判斷：用幾個關鍵維度組合出「可說的故事」
    rt = dims.get("風險承受度") or 50
    sec = dims.get("保障安全感需求") or 50
    plan = dims.get("長期規劃程度") or 50

    if rt >= 70 and plan >= 65 and sec <= 55:
        ptype = "成長進取型"
        reason = "你願意承擔波動換取長期成長，且具備規劃能力；適合以「保障打底 + 成長配置」的方式布局。"
    elif sec >= 70 and rt <= 55:
        ptype = "穩健防禦型"
        reason = "你優先追求可預期與安全感，風險承受度較保守；適合先把醫療/意外/重大傷病缺口補齊。"
    elif sec >= 65 and plan >= 65:
        ptype = "責任規劃型"
        reason = "你重視保障與長期可控，願意用規劃降低不確定性；適合分層保費、分階段完成保障與資產目標。"
    else:
        ptype = "均衡務實型"
        reason = "你在風險與穩定間取得平衡，會兼顧眼前需求與長期目標；適合用核心保障穩住，再做彈性加值。"

    confidence = int(round((answered / 10) * 100))

    radar_labels = list(dims.keys())
    radar_data = [dims[k] if dims[k] is not None else 0 for k in radar_labels]

    bar_labels = [f"Q{i}" for i in range(1, 11)]
    bar_data = [v if v is not None else 0 for v in q100]

    return {
        "profile": {"Type": ptype, "Reason": reason[:110]},
        "confidence": confidence,
        "answered_n": answered,
        "total_n": 10,
        "dims": dims,
        "charts": {
            "radar": {"labels": radar_labels, "data": radar_data},
            "bar": {"labels": bar_labels, "data": bar_data},
        },
    }


def _values_fallback_report(metrics: Dict[str, Any]) -> Dict[str, Any]:
    p = metrics.get("profile", {})
    dims = metrics.get("dims", {}) or {}

    def _d(k: str) -> int:
        v = dims.get(k)
        return int(v) if isinstance(v, int) else 50

    insights = [
        f"你的「風險承受度」約 {_d('風險承受度')}/100，代表你在波動與報酬間的態度偏向 {'進取' if _d('風險承受度')>=70 else '保守' if _d('風險承受度')<=45 else '中性'}。",
        f"「保障安全感需求」約 {_d('保障安全感需求')}/100，顯示你對突發事件的心理門檻較 {'低' if _d('保障安全感需求')>=70 else '高'}，需要用制度化保障來穩定。",
        f"「長期規劃程度」約 {_d('長期規劃程度')}/100，代表你在目標設定與紀律性上 {'較強' if _d('長期規劃程度')>=65 else '仍可加強'}。",
        f"「健康風險敏感度」約 {_d('健康風險敏感度')}/100，代表你對醫療成本的不確定性 {'敏感' if _d('健康風險敏感度')>=65 else '相對不敏感'}。",
    ]

    strengths = [
        "能用長期視角看待保費與保障，較不容易衝動買錯方向。",
        "對風險有基本認知，願意透過制度（保險/預備金）降低不確定性。",
        "可接受分階段完善配置，不會一次把資源押在單一商品。",
    ]

    blindspots = [
        "容易只看『保費』或只看『保障額度』，忽略除外責任與續保條件。",
        "若有家庭責任，可能低估『收入中斷』帶來的連鎖影響（醫療+生活費）。",
        "若偏進取，可能高估自己的波動承受力，缺少緊急預備金會讓策略失效。",
    ]

    roadmap = [
        {
            "phase": "Phase 1（0–1 個月）",
            "goal": "盤點現況與缺口，先把高頻風險補起來",
            "actions": [
                "盤點既有保單：醫療實支、意外、重大傷病是否齊全且額度合理。",
                "建立緊急預備金（至少 3–6 個月生活費），避免保費或投資策略被迫中斷。",
                "把『必要保障』與『加值規劃』分開：先穩住底層，再談優化。"
            ],
        },
        {
            "phase": "Phase 2（1–3 個月）",
            "goal": "做分層配置：核心保障穩定、彈性項目可調",
            "actions": [
                "核心：醫療 + 意外 + 重大傷病（依你的健康敏感度調整權重）。",
                "家庭責任高者：補壽險/收入替代概念（用定期型更有效率）。",
                "檢查繳費期間與現金流：避免過度壓縮生活品質導致中途停繳。"
            ],
        },
        {
            "phase": "Phase 3（3–12 個月）",
            "goal": "依人生事件迭代（結婚/小孩/換工作/購屋）",
            "actions": [
                "每次人生事件觸發一次『保障校正』：保障額度跟著責任變動。",
                "把保障視為風險管理工具，不與投資績效綁死，降低情緒化決策。",
                "建立年度檢視表：保費占比、保障缺口、條款變動與理賠案例追蹤。"
            ],
        },
    ]

    insurance_advice = [
        "先把醫療實支與重大傷病做成『底盤』，再往意外與長期規劃延伸。",
        "如果你有家庭責任，建議加入定期壽險概念，用較低成本換取高額收入替代。",
        "選商品時，除了保障項目，更要看續保、除外責任、等待期與理賠條件。"
    ]

    return {
        "status": "success",
        "quiz_id": "values",
        "value_profile": p or {"Type": "均衡務實型", "Reason": "資料不足，先以均衡策略建議。"},
        "insights": insights[:5],
        "strengths": strengths[:3],
        "blindspots": blindspots[:3],
        "roadmap": roadmap,
        "insurance_advice": insurance_advice[:3],
        "value_metrics": metrics,
    }


# =========================
# Routes：頁面
# =========================
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/quiz/<quiz_id>")
def quiz_entry(quiz_id: str):
    quiz_id = (quiz_id or "").lower().strip()
    if quiz_id not in ("insurance", "values"):
        abort(404)

    if quiz_id == "insurance":
        return render_template("main_questionnaire.html", quiz_id="insurance", quiz_title="推薦保單系統")
    else:
        return render_template("questionnaire.html", quiz_id="values", quiz_title="價值觀分析系統")


@app.route("/result/<user_id>")
def result_page(user_id: str):
    result_data = AI_RESULT_STORE.get(user_id)
    if not result_data:
        return render_template("result_display.html", error="找不到該用戶的分析結果，請重新填寫。")
    return render_template("result_display.html", final_result=result_data)


@app.route("/product/<product_id>")
def product_detail(product_id: str):
    p = get_product_by_id(product_id)
    if not p:
        return render_template("product_detail.html", error="找不到此商品，可能資料庫沒有該商品或 ID 不正確。")
    return render_template("product_detail.html", product=p)


# =========================
# Routes：API
# =========================
@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"status": "error", "message": "未收到任何數據"}), 400

    explicit_quiz = (data.get("quiz_id") or data.get("quiz") or "values").lower().strip()
    answers = data.get("answers")
    if answers is None:
        answers = data  # 兼容舊版

    quiz_id = _infer_quiz_id_from_answers(explicit_quiz, answers)

    user_id = str(len(USER_DATA_STORE) + 1)
    USER_DATA_STORE[user_id] = {"quiz_id": quiz_id, "answers": answers}

    

    try:
        # =========================
        # 推薦保單系統：規則+DB+AI文案
        # =========================
        if quiz_id == "insurance":
            scoring = compute_insurance_scoring(answers)

            q2_choice = ""
            if isinstance(answers.get("Q2"), dict):
                q2_choice = answers.get("Q2", {}).get("choice") or ""
            user_meta = {"age": _age_group_to_age(q2_choice)}

            products = recommend_top3_products(scoring, user_meta=user_meta)
            products = attach_riders_to_mains(products, scoring, user_meta=user_meta, limit=2)

            payload_obj = {
                "quiz_id": "insurance",
                "answers": answers,
                "scoring_result": {
                    "top_categories": scoring.get("top_categories", []),
                    "scores": scoring.get("scores", {}),
                    "channels": scoring.get("channels", {}),
                    "meta": scoring.get("meta", {}),
                },
                "recommended_products": products,
            }

            ai_input = json.dumps(payload_obj, ensure_ascii=False, indent=2)
            ai_text = call_ollama_api(SYSTEM_PROMPT_INSURANCE, ai_input)
            ai_data = _safe_parse_json(ai_text)

            if ai_data.get("status") != "success":
                ai_data = {
                    "status": "success",
                    "quiz_id": "insurance",
                    "person_summary": "（AI 文案解析失敗，以下為系統依問卷規則產生的推薦結果。）",
                    "top_categories": [
                        {"name": c.get("name") or c.get("key") or "未提供", "reason": (c.get("reason") or "")[:30]}
                        for c in scoring.get("top_categories", [])
                    ][:3],
                    "next_step": [
                        "如需更精準建議，可補充：目前保單狀況、預算、是否有家族病史。",
                        "確認保障缺口：醫療實支、重大傷病、長照、意外、壽險。",
                        "先選主約再挑附約，避免保障重複或保費失衡。",
                    ],
                    "product_advice": [
                        "比較重點：承保年齡、繳費期間、保障範圍與除外責任。",
                        "若有多個類別需求，優先補齊醫療與意外，再做長期與資產規劃。",
                        "附約/條款建議搭配主約選擇，並確認是否可附加與續保條件。",
                    ],
                }

            ai_data.setdefault("quiz_id", "insurance")
            ai_data.setdefault("person_summary", "（系統未回傳完整摘要）")

            if not ai_data.get("top_categories"):
                ai_data["top_categories"] = [
                    {"name": c.get("name") or c.get("key"), "reason": (c.get("reason") or "")[:30]}
                    for c in scoring.get("top_categories", [])
                ][:3]

            ai_data.setdefault("next_step", [])
            ai_data.setdefault("product_advice", [])
            ai_data["recommended_products"] = products or []

            AI_RESULT_STORE[user_id] = ai_data
            return jsonify({"status": "success", "user_id": user_id}), 200

        # =========================
        # 價值觀分析：量化 metrics + AI 報告（失敗就 fallback）
        # =========================
        else:
            payload_obj = {"quiz_id": "values", "answers": answers}
            ai_input = json.dumps(payload_obj, ensure_ascii=False, indent=2)
            ai_text = call_ollama_api(SYSTEM_PROMPT_VALUES, ai_input)
            ai_data = _safe_parse_json(ai_text)

            ai_data.setdefault("value_profile", {"Type": "未知", "Reason": "AI 回傳格式不完整"})
            ai_data.setdefault("insurance_advice", [])

            # ✅ 關鍵：塞進量化指標（圖表用）
            ai_data["value_metrics"] = compute_value_metrics(answers)

            AI_RESULT_STORE[user_id] = ai_data
            return jsonify({"status": "success", "user_id": user_id}), 200


    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/db_check")
def db_check():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        count = None
        if "policies" in tables:
            cur.execute("SELECT COUNT(*) FROM policies")
            count = cur.fetchone()[0]
        return jsonify({"status": "ok", "tables": tables, "policies_count": count}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        try:
            conn.close()
        except:
            pass


if __name__ == "__main__":
    print("Server starting on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)