import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import twstock
import requests

# 設定網頁版面
st.set_page_config(page_title="台股進階全方位分析工具", layout="wide")

st.title("📈 台股進階全方位分析網頁工具")
st.markdown("基本面與證交所API自動串接 + 布林通道優化策略 + ETF折溢價評估 + 回測績效評估")

# 1. 初始化網頁端的動態自選股清單
if 'custom_watchlist' not in st.session_state:
    st.session_state.custom_watchlist = {
        "台積電 (2330)": "2330",
        "鴻海 (2317)": "2317",
        "元大台灣50 (0050)": "0050",
        "國泰永續高股息 (00878)": "00878",
        "聯發科 (2454)": "2454",
        "廣達 (2382)": "2382"
    }

st.sidebar.header("⭐ 自選股管理與切換")

# 新增自選股功能
with st.sidebar.expander("➕ 新增自選股"):
    new_name = st.text_input("股票名稱 (例: 聯詠)", value="", placeholder="可填寫公司名稱")
    new_code = st.text_input("台股代號 (例: 3034)", value="", placeholder="輸入數字代號")
    if st.button("確認加入"):
        if new_code.strip():
            code_clean = new_code.strip().upper().replace(".TW", "").replace(".TWO", "")
            auto_name = twstock.codes[code_clean].name if code_clean in twstock.codes else new_name.strip()
            label = f"{auto_name} ({code_clean})"
            st.session_state.custom_watchlist[label] = code_clean
            st.success(f"已成功新增 {label}！")
            st.rerun()
        else:
            st.warning("請至少輸入股票代號！")

# 刪除自選股功能
with st.sidebar.expander("🗑️ 刪除自選股"):
    if len(st.session_state.custom_watchlist) > 1:
        stock_to_delete = st.selectbox("選擇要刪除的股票", list(st.session_state.custom_watchlist.keys()))
        if st.button("確認刪除此股票"):
            del st.session_state.custom_watchlist[stock_to_delete]
            st.success(f"已刪除 {stock_to_delete}！")
            st.rerun()
    else:
        st.info("清單中至少需保留一檔股票。")

st.sidebar.markdown("---")

selected_stock = st.sidebar.radio("點擊直接切換股票：", list(st.session_state.custom_watchlist.keys()), index=0)
default_ticker = st.session_state.custom_watchlist[selected_stock]

st.sidebar.markdown("---")
st.sidebar.header("🔍 手動輸入與回測設定")
stock_input = st.sidebar.text_input("直接輸入其他代號 (例: 2330 或 0050)", value=default_ticker)

# 回測天數設定
backtest_days = st.sidebar.number_input(
    "顯示/回測天數 (交易日)", 
    min_value=20, 
    max_value=2500, 
    value=250, 
    step=10,
    help="輸入您想檢視與回測的歷史交易日天數（例如 250 天約等於一年）"
)

# 賣出策略條件選擇器
st.sidebar.markdown("---")
st.sidebar.header("⚙️ 賣出訊號過濾機制選擇")
sell_strategy = st.sidebar.selectbox(
    "選擇賣出條件嚴格度",
    ["1. 精準波段 (觸及布林上軌 或 RSI>75 賣出) [推薦-過濾雜訊]", 
     "2. 趨勢防守 (跌破 60MA 季線 或 觸及上軌 賣出)",
     "3. 寬鬆波段 (僅觸及布林上軌時 賣出)"]
)

# 清理代號格式並自動加上 .TW
clean_stock_code = stock_input.strip().upper().replace(".TW", "").replace(".TWO", "")
stock_code = clean_stock_code + ".TW"

# 自動從證交所官方 API 抓取本益比與殖利率的函數
def fetch_twse_data(stock_no):
    try:
        url = f"https://www.twse.com.tw/rwd/zh/BWIBBU/BWIBBU?response=json&stockNo={stock_no}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        
        if data.get('stat') == 'OK' and 'data' in data and len(data['data']) > 0:
            latest_row = data['data'][-1]
            fields = data.get('fields', [])
            row_dict = {fields[i]: latest_row[i] for i in range(len(fields))}
            
            pe, dy = None, None
            for k, v in row_dict.items():
                if '本益比' in k: pe = v
                if '殖利率' in k: dy = v
                
            pe_val = float(pe) if pe and pe != '-' else None
            yield_val = float(dy) if dy and dy != '-' else None
            return pe_val, yield_val
    except Exception:
        pass
    return None, None

# 自動從證交所 MIS 抓取 ETF 淨值的函數
def fetch_etf_nav_api(stock_no):
    try:
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_no}.tw"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=3)
        data = res.json()
        if 'msgArray' in data and len(data['msgArray']) > 0:
            nav_str = data['msgArray'][0].get('nav', None)
            if nav_str and nav_str != '-':
                return float(nav_str)
    except Exception:
        pass
    return None

auto_pe, auto_yield = fetch_twse_data(clean_stock_code)

# 基本面數值設定區
st.sidebar.markdown("---")
st.sidebar.header("📊 基本面條件設定")
if auto_pe is not None and auto_yield is not None:
    st.sidebar.success("🔗 已成功從證交所自動同步最新本益比與殖利率！")
    default_pe = auto_pe
    default_yield = auto_yield
else:
    default_pe = 12.0
    default_yield = 4.5

manual_pe = st.sidebar.number_input("本益比 (P/E)", min_value=0.0, value=float(default_pe), step=0.5)
manual_yield = st.sidebar.number_input("殖利率 (%)", min_value=0.0, value=float(default_yield), step=0.1)

if clean_stock_code:
    with st.spinner(f"正在分析代號 {clean_stock_code} 中，請稍候..."):
        try:
            ticker = yf.Ticker(stock_code)
            
            # 取得精準的中文名稱
            if clean_
