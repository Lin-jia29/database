import streamlit as st
import pandas as pd
import sqlite3
from openai import OpenAI
import os
import re
import plotly.graph_objects as go

# --- 1. 初始化與 API Key 安全讀取 ---
st.set_page_config(page_title="南山 AI 智慧顧問", layout="wide", initial_sidebar_state="expanded")

# 從 Streamlit Secrets 讀取 Key (部署到雲端後，請在 Advanced settings 設定)
try:
    API_KEY = st.secrets["OPENAI_API_KEY"]
except:
    st.error("❌ 尚未設定 API Key。請在 Streamlit Cloud 的 Secrets 中填入 OPENAI_API_KEY。")
    st.stop()

client = OpenAI(api_key=API_KEY.strip())

# 初始化 session_state
if "page" not in st.session_state: st.session_state.page = "home"
if "user_type" not in st.session_state: st.session_state.user_type = None
if "search_tags" not in st.session_state: st.session_state.search_tags = []
if "messages" not in st.session_state: 
    st.session_state.messages = [{"role": "system", "content": "你是一位專業保險顧問。請根據對話與性格測驗結果推薦險種。"}]
if "recs" not in st.session_state: st.session_state.recs = []

# --- 2. SQL 資料庫初始化 (自動讀取並清洗) ---
@st.cache_resource
def init_db():
    # 加上 "專題保險/" 前綴
    all_files = [
        "專題保險/投資型保險.xlsx", "專題保險/長期照顧.xlsx", "專題保險/旅行險.xlsx", 
        "專題保險/健康醫療.xlsx", "專題保險/意外傷害.xlsx", "專題保險/團體保險自組商品.xlsx", 
        "專題保險/團體保險套裝商品.xlsx", "專題保險/壽險保障.xlsx", "專題保險/網路投保商品.xlsx", 
        "專題保險/銀行保險商品_投資型.xlsx", "專題保險/銀行保險商品_健康險.xlsx", 
        "專題保險/銀行保險商品_定期險.xlsx", "專題保險/銀行保險商品_終身險(外幣).xlsx", 
        "專題保險/銀行保險商品_終身險(新台幣).xlsx", "專題保險/還本_增額_年金保險.xlsx"
    ]
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    combined_list = []
    
    for f in all_files:
        if os.path.exists(f):
            try:
                df = pd.read_excel(f, engine='openpyxl')
                df.columns = [str(c).strip() for c in df.columns]
                # 統一「保險名稱」欄位
                name_col = [c for c in df.columns if '名稱' in c]
                if name_col:
                    df = df.rename(columns={name_col[0]: '保險名稱'})
                    df['來源檔案'] = f
                    combined_list.append(df)
            except: pass
            
    if combined_list:
        full_df = pd.concat(combined_list, ignore_index=True)
        # 資料清洗：去除名稱缺失、重複項
        full_df = full_df.dropna(subset=['保險名稱'])
        full_df = full_df.drop_duplicates(subset=['保險名稱'], keep='first')
        full_df = full_df.fillna("見條款細節")
        full_df.to_sql('policies', conn, if_exists='replace', index=False)
        return conn, len(full_df)
    return None, 0

conn, db_total = init_db()

# --- 3. 心理測驗頁面 (含動態縮放雷達圖) ---
def show_quiz_page():
    st.title("🧠 投保性格多維度分析")
    st.write("透過五個情境問題，我們將繪製您的專屬雷達圖，為您優化保險推薦演算法。")
    
    with st.form("quiz_form"):
        st.subheader("🌲 森林冒險情境")
        q1 = st.radio("1. 發現神秘岔路，你會？", ["沿著鋪好的路走 (謹慎)", "冒險走進草叢 (冒險)", "先觀察路標 (保障)"])
        q2 = st.radio("2. 突然下雨了，你的背包裡必備的是？", ["足以支撐整天的乾糧 (儲蓄)", "急救包與雨具 (保障)", "一台高級相機 (冒險)"])
        q3 = st.radio("3. 看到受傷的小鹿，你的反應是？", ["確認環境是否安全 (謹慎)", "立刻上前包紮 (保障)", "找專業救援 (儲蓄)"])
        q4 = st.radio("4. 營火晚會時，你喜歡扮演什麼角色？", ["守護火堆的人 (保障)", "策劃活動的人 (冒險)", "靜靜享受的人 (謹慎)"])
        q5 = st.radio("5. 探險結束，你最希望帶走的禮物是？", ["一袋金幣 (儲蓄)", "一本生存指南 (保障)", "一張再次入園的門票 (投資)"])
        
        submitted = st.form_submit_button("送出測驗並分析")
        
        if submitted:
            ans_pool = f"{q1}{q2}{q3}{q4}{q5}"
            scores = {
                "保障": ans_pool.count("保障") * 20 + 10,
                "儲蓄": ans_pool.count("儲蓄") * 20 + 10,
                "投資": ans_pool.count("投資") * 20 + 10,
                "謹慎": ans_pool.count("謹慎") * 20 + 10,
                "冒險": ans_pool.count("冒險") * 20 + 10
            }
            
            # 繪製雷達圖
            categories = list(scores.keys())
            values = list(scores.values())
            values += values[:1] # 閉合
            categories += categories[:1]

            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(
                r=values, theta=categories, fill='toself', 
                line=dict(color='#005496', width=4), 
                fillcolor='rgba(0, 84, 150, 0.4)'
            ))
            fig.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, max(values) + 10]), # 動態縮放更清晰
                    angularaxis=dict(tickfont=dict(size=14, color="white"))
                ),
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)

            # 判定性格
            max_cat = max(scores, key=scores.get)
            st.session_state.user_type = f"{max_cat}導向型"
            type_map = {
                "保障": ["醫療", "意外", "癌症", "住院"],
                "儲蓄": ["還本", "年金", "增額", "終身"],
                "投資": ["投資型", "變額", "美元"],
                "謹慎": ["長照", "壽險", "定期"],
                "冒險": ["投資型", "外幣", "旅行"]
            }
            st.session_state.search_tags = type_map.get(max_cat, [])
            st.success(f"✅ 分析完成！您的性格為：{st.session_state.user_type}")

    if st.session_state.user_type:
        if st.button("⬅️ 完成並回到 AI 顧問對話"):
            st.session_state.page = "home"
            st.rerun()

# --- 4. 主對話頁面 ---
def show_home_page():
    st.title("🛡️ 南山 AI 智慧保險顧問")
    
    with st.sidebar:
        if st.button("🔄 重新做心理測驗", use_container_width=True):
            st.session_state.page = "quiz"
            st.rerun()
        st.divider()
        st.metric("📊 資料庫保單總數", db_total)
        if st.session_state.user_type:
            st.success(f"🧠 您的性格：{st.session_state.user_type}")
            st.caption(f"優先檢索：{', '.join(st.session_state.search_tags)}")

    col_chat, col_card = st.columns([6, 4])

    with col_chat:
        for msg in st.session_state.messages[1:]:
            with st.chat_message(msg["role"]): st.write(msg["content"])

        if prompt := st.chat_input("請描述您的需求 (例如：我30歲，想找美元儲蓄險)"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.write(prompt)

            with st.chat_message("assistant"):
                resp = client.chat.completions.create(model="gpt-4o", messages=st.session_state.messages)
                ans = resp.choices[0].message.content
                st.write(ans)
                st.session_state.messages.append({"role": "assistant", "content": ans})

            # SQL 檢索聯動
            age_match = re.search(r'(\d+)歲', prompt + ans)
            age = age_match.group(1) if age_match else None
            user_keywords = [t for t in ["醫療", "意外", "癌症", "壽險", "投資", "年金", "美元", "台幣"] if t in prompt + ans]
            final_tags = list(set(st.session_state.search_tags + user_keywords))

            query = "SELECT * FROM policies WHERE 1=1"
            if final_tags:
                tag_cond = " OR ".join([f"保險名稱 LIKE '%{t}%' OR 說明 LIKE '%{t}%'" for t in final_tags])
                query += f" AND ({tag_cond})"
            if age:
                query += f" AND 承保年齡 LIKE '%{age}%'"
            
            st.session_state.recs = pd.read_sql_query(query + " LIMIT 8", conn).to_dict('records')
            st.rerun()

    with col_card:
        st.subheader("📋 專屬推薦清單")
        if not st.session_state.recs:
            st.info("💡 歡迎描述需求，AI 將為您精選最合適的保單。")
        for item in st.session_state.recs:
            with st.container(border=True):
                st.markdown(f"**{item['保險名稱']}**")
                st.caption(f"📁 來源：{item['來源檔案']} | 🎂 年齡：{item.get('承保年齡','依條款')}")
                with st.expander("🔍 詳情與給付項目"):
                    st.write(f"**產品特色：**\n{item.get('說明','請洽業務員')}")
                    st.divider()
                    st.write(f"**主要給付項目：**\n{item.get('賠償項目','請參閱條款')}")

# --- 5. 頁面切換控制 ---
if conn:
    if st.session_state.page == "home":
        show_home_page()
    else:
        show_quiz_page()
else:
    st.error("❌ 無法載入保單資料，請確認 Excel 檔案是否存在於 GitHub 資料夾中。")
