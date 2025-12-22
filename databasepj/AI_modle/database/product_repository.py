# AI_modle/database/product_repository.py
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


# -------------------------
# DB 連線
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(BASE_DIR, "..", "product.db"))

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

_PLACEHOLDERS = {"見條款細節", "未提供", "請參閱保單條款", "請參閱條款", "依條款", "依條款細節"}

def _clean(v):
    s = ("" if v is None else str(v)).strip()
    return "" if (not s or s in _PLACEHOLDERS) else s


# -------------------------
# 分類關鍵字（用於 policies 搜尋）
# -------------------------
CATEGORY_KEYWORDS = {
    "health_medical": ["健康", "醫療", "住院", "實支", "重大傷病", "癌症", "醫療險"],
    "accident": ["意外", "傷害", "骨折", "燒燙傷", "意外險"],
    "travel": ["旅行", "旅平", "旅遊", "海外", "出發地點"],
    "long_term_care": ["長期照顧", "長照", "失能", "照護"],
    "life": ["壽險", "定期", "終身", "身故", "壽"],
    "investment": ["投資", "投資型", "外幣", "美元", "變額"],
    "group": ["團體保險", "團保", "員工", "公司員工"],
    "online": ["網路投保", "網路"],
    "bank": ["銀行保險", "銀行"],
}


# -------------------------
# 工具：從 scoring 抽類別 key
# -------------------------
def _pick_category_keys(scoring: Dict[str, Any]) -> List[str]:
    keys = []
    for c in (scoring or {}).get("top_categories", []) or []:
        k = (c.get("key") or c.get("name") or c.get("id") or "").strip()
        if k:
            keys.append(k)
    return keys


def _normalize_category_keys(category_keys: List[str]) -> List[str]:
    normalized: List[str] = []
    for k in category_keys:
        lk = str(k).lower()

        if lk in CATEGORY_KEYWORDS:
            normalized.append(lk)
            continue

        # 常見中文/非標準 key fallback
        if ("醫療" in k) or ("健康" in k):
            normalized.append("health_medical")
        elif "意外" in k:
            normalized.append("accident")
        elif ("旅行" in k) or ("旅" in k):
            normalized.append("travel")
        elif ("長照" in k) or ("照顧" in k) or ("失能" in k):
            normalized.append("long_term_care")
        elif "壽" in k:
            normalized.append("life")
        elif ("投資" in k) or ("外幣" in k) or ("美元" in k):
            normalized.append("investment")
        elif ("團體" in k) or ("團保" in k):
            normalized.append("group")
        elif "網路" in k:
            normalized.append("online")
        elif "銀行" in k:
            normalized.append("bank")

    # 去重但保留順序
    seen = set()
    out = []
    for x in normalized:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


# -------------------------
# 工具：年齡判斷（解析 policies.承保年齡）
# -------------------------
def _extract_numbers(s: str) -> List[int]:
    return [int(x) for x in re.findall(r"\d+", s or "")]

def _age_ok(insured_age_text: str, age: Optional[int]) -> bool:
    """
    policies 的 承保年齡 欄位格式不一致，因此採「能判斷就判斷，不能判斷就放行」。
    """
    if age is None:
        return True
    t = (insured_age_text or "").strip()
    if not t:
        return True

    nums = _extract_numbers(t)

    # 常見：0-70 / 0~70 / 0–70 / 0-70歲
    if len(nums) >= 2:
        mn, mx = nums[0], nums[1]
        if mn > mx:
            mn, mx = mx, mn
        return mn <= age <= mx

    # 只有一個數字：可能是「最高70歲」或「滿20歲」
    if len(nums) == 1:
        n = nums[0]
        # 若文字包含 "以上/起/滿"：代表最低門檻
        if any(x in t for x in ["以上", "起", "滿", "至少"]):
            return age >= n
        # 若文字包含 "以下/至/不超過"：代表最高上限
        if any(x in t for x in ["以下", "至", "不超過", "內"]):
            return age <= n
        # 無法判斷，放行
        return True

    return True


# -------------------------
# 工具：推斷通路（你的 DB 沒有通路欄位，用來源檔案推）
# -------------------------
def _infer_channel(source_file: str) -> str:
    s = (source_file or "").lower()
    if "網路" in s:
        return "網路"
    if "銀行" in s:
        return "銀行"
    if "團體" in s or "團保" in s:
        return "團體"
    return "一般"


# -------------------------
# 從 policies 撈候選
# -------------------------
def _fetch_candidates_by_keywords(
    conn: sqlite3.Connection,
    keywords: List[str],
    age: Optional[int] = None,
    limit: int = 80,
) -> List[Dict[str, Any]]:
    if not keywords:
        return []

    cur = conn.cursor()

    # WHERE：保險名稱/說明/來源檔案 任一命中
    where_parts = []
    params: List[Any] = []
    for kw in keywords:
        kw = (kw or "").strip()
        if not kw:
            continue

        sub = ["保險名稱 LIKE ?"]
        params.append(f"%{kw}%")

        # 你的 policies 一定有這兩欄（你已確認）
        sub.append("說明 LIKE ?")
        params.append(f"%{kw}%")

        sub.append("來源檔案 LIKE ?")
        params.append(f"%{kw}%")

        where_parts.append("(" + " OR ".join(sub) + ")")

    if not where_parts:
        return []

    sql = f"""
        SELECT rowid AS product_id, *
        FROM policies
        WHERE {" OR ".join(where_parts)}
        LIMIT {int(limit)}
    """
    cur.execute(sql, params)
    rows = cur.fetchall()

    results: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)

        # 年齡二次過濾（避免 LIKE 失準）
        if not _age_ok(d.get("承保年齡", ""), age):
            continue

        # ===== 統一欄位（模板/前端會用到）=====
        d["product_id"] = d.get("product_id")
        d["product_name"] = d.get("保險名稱") or "（未命名商品）"
        d["main_rider"] = d.get("主約/附約/附加條款/批註條款") or ""

        d["currency"] = d.get("幣別") or ""
        d["insure_age"] = d.get("承保年齡") or ""
        d["pay_type"] = d.get("繳費方式") or ""
        d["pay_period"] = d.get("繳費期間") or ""

        d["description"] = d.get("說明") or ""
        d["note"] = d.get("註記") or ""
        d["benefits"] = d.get("賠償項目") or ""

        d["source"] = d.get("來源檔案") or ""

        # 旅行/特殊欄位
        d["departure"] = d.get("出發地點") or ""
        d["insurance_period"] = d.get("保險期間") or ""
        d["target"] = d.get("該保險提供對象") or ""

        d["product_code"] = d.get("商品代號") or ""
        d["terms"] = d.get("商品條款") or ""

        # 你 DB 沒這兩欄，先補
        d["gender_limit"] = ""
        d["channel"] = _infer_channel(d.get("source", ""))

        # 附約目前無關聯
        d["riders"] = []

        results.append(d)  # ✅ 這行是你之前漏掉，導致推薦永遠空

    return results


def _fetch_fallback_any(conn: sqlite3.Connection, age: Optional[int], limit: int = 120) -> List[Dict[str, Any]]:
    """
    當分類關鍵字找不到東西時，至少抓一些商品出來避免空畫面。
    """
    cur = conn.cursor()
    sql = f"""
        SELECT rowid AS product_id, *
        FROM policies
        ORDER BY rowid DESC
        LIMIT {int(limit)}
    """
    cur.execute(sql)
    rows = cur.fetchall()

    results: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if not _age_ok(d.get("承保年齡", ""), age):
            continue

        d["product_id"] = d.get("product_id")
        d["product_name"] = d.get("保險名稱") or "（未命名商品）"
        d["main_rider"] = d.get("主約/附約/附加條款/批註條款") or ""
        d["currency"] = d.get("幣別") or ""
        d["insure_age"] = d.get("承保年齡") or ""
        d["pay_type"] = d.get("繳費方式") or ""
        d["pay_period"] = d.get("繳費期間") or ""
        d["description"] = d.get("說明") or ""
        d["benefits"] = d.get("賠償項目") or ""
        d["source"] = d.get("來源檔案") or ""
        d["channel"] = _infer_channel(d.get("source", ""))
        d["riders"] = []
        results.append(d)

    return results


# -------------------------
# 對外 API：推薦 Top3
# -------------------------
def recommend_top3_products(
    scoring: Dict[str, Any],
    user_meta: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    user_meta = user_meta or {}
    age = user_meta.get("age")

    category_keys = _pick_category_keys(scoring)
    normalized_keys = _normalize_category_keys(category_keys)

    if not normalized_keys:
        normalized_keys = ["health_medical", "accident", "life"]

    conn = get_db_connection()
    try:
        picked: List[Dict[str, Any]] = []
        used_ids = set()

        for key in normalized_keys:
            keywords = CATEGORY_KEYWORDS.get(key, [])
            cands = _fetch_candidates_by_keywords(conn, keywords, age=age, limit=120)

            # 依「關鍵字命中數」粗略排序（越多越前）
            def score_item(x: Dict[str, Any]) -> int:
                text = (x.get("product_name", "") + " " + x.get("description", "") + " " + x.get("source", ""))
                s = 0
                for kw in keywords:
                    if kw and (kw in text):
                        s += 1
                return s

            cands.sort(key=score_item, reverse=True)

            for c in cands:
                pid = c.get("product_id")
                if pid in used_ids:
                    continue
                used_ids.add(pid)
                picked.append(c)
                break

            if len(picked) >= 3:
                break

        # 不足 3 個：用 fallback 補齊
        if len(picked) < 3:
            fallback = _fetch_fallback_any(conn, age=age, limit=200)
            for c in fallback:
                pid = c.get("product_id")
                if pid in used_ids:
                    continue
                used_ids.add(pid)
                picked.append(c)
                if len(picked) >= 3:
                    break

        return picked[:3]
    finally:
        conn.close()


# -------------------------
# 對外 API：附約（先保底不做，避免炸）
# -------------------------
def attach_riders_to_mains(
    mains: List[Dict[str, Any]],
    scoring: Dict[str, Any],
    user_meta: Optional[Dict[str, Any]] = None,
    limit: int = 2
) -> List[Dict[str, Any]]:
    # 目前 policies 無「附約關聯」，先保底回空 riders
    for m in mains or []:
        m.setdefault("riders", [])
    return mains or []


# -------------------------
# 對外 API：商品詳情（/product/<id>）
# -------------------------
def get_product_by_id(product_id: Any) -> Optional[Dict[str, Any]]:
    # product_id 可能是字串，這裡盡量轉 int
    try:
        pid = int(str(product_id).strip())
    except Exception:
        pid = product_id

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT rowid AS product_id, * FROM policies WHERE rowid = ?", (pid,))
        row = cur.fetchone()
        if not row:
            return None

        d = dict(row)

        # ===== 統一欄位（商品詳情頁會用到）=====
        d["product_id"] = d.get("product_id")
        d["product_name"] = d.get("保險名稱") or "（未命名商品）"

        d["main_rider"] = d.get("主約/附約/附加條款/批註條款") or ""
        d["currency"] = d.get("幣別") or ""
        d["insure_age"] = d.get("承保年齡") or ""
        d["pay_type"] = d.get("繳費方式") or ""
        d["pay_period"] = d.get("繳費期間") or ""

        d["description"] = d.get("說明") or ""
        d["note"] = d.get("註記") or ""
        d["benefits"] = d.get("賠償項目") or ""

        d["source"] = d.get("來源檔案") or ""
        d["channel"] = _infer_channel(d.get("source", ""))

        d["departure"] = d.get("出發地點") or ""
        d["insurance_period"] = d.get("保險期間") or ""
        d["target"] = d.get("該保險提供對象") or ""

        d["product_code"] = d.get("商品代號") or ""
        d["terms"] = d.get("商品條款") or ""

        d["gender_limit"] = ""
        d.setdefault("riders", [])
        return d
    finally:
        conn.close()
