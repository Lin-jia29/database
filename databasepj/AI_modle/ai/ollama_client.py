# AI_modle/ai/ollama_client.py
import os
import re
import json
from typing import Any, Dict, Optional

import requests
import json5


# =========================
# 基本設定（可用環境變數覆蓋）
# =========================
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b-instruct-q4_k_m")
DEFAULT_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))


# =========================
# 工具：從文字中抽出第一個 JSON 物件
# =========================
def _extract_first_json_object(text: str) -> str:
    """
    從模型回應中抽出第一個完整 JSON 物件（最外層 {...}）。
    具備容錯：即使前後多了幾句話、或包了 ```json 也能抽出來。
    """
    if not text:
        raise ValueError("AI 回應為空")

    t = text.strip()

    # 去掉 code fence（保險）
    t = re.sub(r"```json", "", t, flags=re.IGNORECASE).strip()
    t = t.replace("```", "").strip()

    # 找到第一個 '{'
    start = t.find("{")
    if start == -1:
        raise ValueError(f"找不到 JSON 開頭 '{{'：{t[:200]}")

    # 用括號計數找出第一個完整 JSON 物件
    depth = 0
    in_str = False
    escape = False

    for i in range(start, len(t)):
        ch = t[i]

        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return t[start : i + 1]

    raise ValueError(f"JSON 物件未閉合，無法解析：{t[start:start+200]}")


# =========================
# 核心：呼叫 Ollama
# =========================
def _post_ollama_generate(
    model: str,
    system_prompt: str,
    user_prompt: str,
    url: str = DEFAULT_OLLAMA_URL,
    timeout: int = DEFAULT_TIMEOUT,
    temperature: float = 0.0,
    force_json: bool = True,
) -> str:
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": user_prompt,
        "system": system_prompt,
        "stream": False,
        "options": {
            "temperature": temperature
        }
    }

    # 強制 JSON（最重要：避免 /submit 解析炸掉）
    if force_json:
        payload["format"] = "json"

    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()

    data = resp.json()

    # Ollama /api/generate 正常會有 response 欄位
    if "response" not in data:
        raise RuntimeError(f"Ollama 回應格式非預期（缺 response）：{str(data)[:300]}")

    return (data.get("response") or "").strip()


# =========================
# 對外：給 app.py 用的函式（保持相容性）
# =========================
def call_ollama_api(
    system_prompt: str,
    user_input_json: str,
    model: str = DEFAULT_MODEL,
    url: str = DEFAULT_OLLAMA_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """
    回傳「乾淨的 JSON 字串」給外部再 json/json5.loads。
    這個名稱刻意保留常見用法，避免你 app.py import 後爆掉。
    """
    prompt = f"以下是完整的用戶問卷數據（JSON）:\n{user_input_json}\n\n請只輸出純 JSON："

    try:
        full_response = _post_ollama_generate(
            model=model,
            system_prompt=system_prompt,
            user_prompt=prompt,
            url=url,
            timeout=timeout,
            temperature=0.0,
            force_json=True,
        )

        # 1) 先嘗試直接解析（因為 format=json 通常會是純 JSON）
        try:
            _ = json5.loads(full_response)
            return full_response
        except Exception:
            pass

        # 2) 容錯：抽出 JSON 再回傳
        json_str = _extract_first_json_object(full_response)
        _ = json5.loads(json_str)  # 再驗證一次，確保回傳的是可解析的 JSON
        return json_str

    except Exception as e:
        # 這裡不要吞錯，讓 /submit 能拿到明確原因
        raise Exception(f"AI 分析失敗：{e}")


def call_ollama_json(
    system_prompt: str,
    user_input: Dict[str, Any],
    model: str = DEFAULT_MODEL,
    url: str = DEFAULT_OLLAMA_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    你如果想要「直接回 dict」可用這個。
    """
    user_input_json = json.dumps(user_input, ensure_ascii=False, indent=2)
    s = call_ollama_api(system_prompt, user_input_json, model=model, url=url, timeout=timeout)
    return json5.loads(s)


# 相容別名（避免你其他檔案用不同名字）
call_ollama = call_ollama_api
