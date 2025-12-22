# merge_excels_to_one.py
# 功能：把 nanshan_xlsx/ 內所有 Excel 合併成 nanshan_all.xlsx（保留來源檔案欄位）
# 用法：python merge_excels_to_one.py

import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XLSX_DIR = os.path.join(BASE_DIR, "nanshan_xlsx")
OUT_FILE = os.path.join(BASE_DIR, "nanshan_all.xlsx")

# 你資料夾裡的檔名清單（照你提供的）
ALL_FILES = [
    "投資型保險.xlsx", "長期照顧.xlsx", "旅行險.xlsx", "健康醫療.xlsx",
    "意外傷害.xlsx", "團體保險自組商品.xlsx", "團體保險套裝商品.xlsx",
    "壽險保障.xlsx", "網路投保商品.xlsx", "銀行保險商品_投資型.xlsx",
    "銀行保險商品_健康險.xlsx", "銀行保險商品_定期險.xlsx",
    "銀行保險商品_終身險(外幣).xlsx", "銀行保險商品_終身險(新台幣).xlsx",
    "還本 增額 年金保險.xlsx"
]

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # 1) 欄位名稱去空白
    df.columns = [str(c).strip() for c in df.columns]

    # 2) 找「名稱」欄位，統一成「保險名稱」
    name_cols = [c for c in df.columns if "名稱" in c]
    if name_cols:
        df = df.rename(columns={name_cols[0]: "保險名稱"})

    return df

def main():
    if not os.path.isdir(XLSX_DIR):
        raise FileNotFoundError(f"找不到資料夾：{XLSX_DIR}")

    combined = []
    missing = []

    for fname in ALL_FILES:
        fpath = os.path.join(XLSX_DIR, fname)
        if not os.path.exists(fpath):
            missing.append(fname)
            continue

        try:
            df = pd.read_excel(fpath, engine="openpyxl")
            df = _normalize_columns(df)

            # 沒有保險名稱就跳過（避免亂合併）
            if "保險名稱" not in df.columns:
                print(f"[跳過] {fname}：找不到『保險名稱』欄位（或沒有任何『名稱』欄位）")
                continue

            df["來源檔案"] = fname
            combined.append(df)
            print(f"[讀取] {fname}：{len(df)} 筆")

        except Exception as e:
            print(f"[錯誤] 讀取 {fname} 失敗：{e}")

    if not combined:
        print("沒有任何檔案成功合併，請確認 nanshan_xlsx 內 Excel 是否存在且可讀取。")
        return

    full_df = pd.concat(combined, ignore_index=True)

    # 清洗：保險名稱空值刪除、去重、補空
    full_df = full_df.dropna(subset=["保險名稱"])
    full_df["保險名稱"] = full_df["保險名稱"].astype(str).str.strip()
    full_df = full_df[full_df["保險名稱"] != ""]
    full_df = full_df.drop_duplicates()
    full_df = full_df.drop_duplicates(subset=["保險名稱"], keep="first")
    full_df = full_df.fillna("見條款細節")

    # 輸出合併檔
    full_df.to_excel(OUT_FILE, index=False, engine="openpyxl")
    print(f"\n[完成] 合併輸出：{OUT_FILE}")
    print(f"[完成] 合併總筆數：{len(full_df)}")

    if missing:
        print("\n[提醒] 下列檔案不存在（可忽略或補齊）：")
        for m in missing:
            print(f" - {m}")

if __name__ == "__main__":
    main()
