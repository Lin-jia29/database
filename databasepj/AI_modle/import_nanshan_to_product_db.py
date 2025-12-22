# import_nanshan_to_product_db.py
# 功能：把 nanshan_all.xlsx（或直接讀 nanshan_xlsx/）匯入到 product.db 的 policies 表
# 用法：python import_nanshan_to_product_db.py

import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "product.db")
MERGED_XLSX = os.path.join(BASE_DIR, "nanshan_all.xlsx")
XLSX_DIR = os.path.join(BASE_DIR, "nanshan_xlsx")

ALL_FILES = [
    "投資型保險.xlsx", "長期照顧.xlsx", "旅行險.xlsx", "健康醫療.xlsx",
    "意外傷害.xlsx", "團體保險自組商品.xlsx", "團體保險套裝商品.xlsx",
    "壽險保障.xlsx", "網路投保商品.xlsx", "銀行保險商品_投資型.xlsx",
    "銀行保險商品_健康險.xlsx", "銀行保險商品_定期險.xlsx",
    "銀行保險商品_終身險(外幣).xlsx", "銀行保險商品_終身險(新台幣).xlsx"
]

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    name_cols = [c for c in df.columns if "名稱" in c]
    if name_cols:
        df = df.rename(columns={name_cols[0]: "保險名稱"})
    return df

def load_dataframe() -> pd.DataFrame:
    # 優先用合併檔（最快）
    if os.path.exists(MERGED_XLSX):
        df = pd.read_excel(MERGED_XLSX, engine="openpyxl")
        df = _normalize_columns(df)
        if "來源檔案" not in df.columns:
            df["來源檔案"] = "nanshan_all.xlsx"
        return df

    # 沒有合併檔就直接掃資料夾合併
    if not os.path.isdir(XLSX_DIR):
        raise FileNotFoundError(f"找不到資料夾：{XLSX_DIR}")

    combined = []
    for fname in ALL_FILES:
        fpath = os.path.join(XLSX_DIR, fname)
        if not os.path.exists(fpath):
            continue
        df = pd.read_excel(fpath, engine="openpyxl")
        df = _normalize_columns(df)
        if "保險名稱" not in df.columns:
            continue
        df["來源檔案"] = fname
        combined.append(df)

    if not combined:
        raise RuntimeError("沒有任何 Excel 成功讀取；請確認 nanshan_xlsx 內檔案存在且格式正確。")

    return pd.concat(combined, ignore_index=True)

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if "保險名稱" not in df.columns:
        raise RuntimeError("資料中找不到『保險名稱』欄位，無法匯入。")

    df = df.dropna(subset=["保險名稱"])
    df["保險名稱"] = df["保險名稱"].astype(str).str.strip()
    df = df[df["保險名稱"] != ""]
    df = df.drop_duplicates()
    df = df.drop_duplicates(subset=["保險名稱"], keep="first")
    df = df.fillna("見條款細節")

    # 全部先轉成字串比較安全（避免 SQLite 型別混亂、以及顯示 NaN）
    for c in df.columns:
        df[c] = df[c].astype(str)

    return df

def import_to_sqlite(df: pd.DataFrame):
    conn = sqlite3.connect(DB_FILE)
    try:
        # policies 表：直接 replace（只會覆蓋 policies，不會動到其他表）
        df.to_sql("policies", conn, if_exists="replace", index=False)

        # 建索引加速 LIKE 查詢（可有可無，但一般會更快）
        cur = conn.cursor()
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_policies_name ON policies(保險名稱);")
        except Exception:
            pass

        conn.commit()
    finally:
        conn.close()

def main():
    df = load_dataframe()
    df = clean_dataframe(df)
    import_to_sqlite(df)

    print(f"[完成] 已匯入 product.db -> policies")
    print(f"[完成] 筆數：{len(df)}")
    print(f"[完成] 資料庫位置：{DB_FILE}")

if __name__ == "__main__":
    main()
