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
            if clean_stock_code in twstock.codes:
                chinese_name = twstock.codes[clean_stock_code].name
            else:
                chinese_name = clean_stock_code

            # 判斷是否為 ETF
            is_etf = clean_stock_code.startswith("00") or "ETF" in chinese_name.upper()

            st.header(f"📌 當前分析目標：{chinese_name} ({clean_stock_code}) {'【ETF專區】' if is_etf else ''}")

            fetch_period = "5y" if backtest_days > 500 else ("2y" if backtest_days > 250 else "1y")
            df = ticker.history(period=fetch_period)
            
            # 【關鍵修復】自動清洗末端可能產生的 NaN 空值，確保抓到的必然是最新有效價格
            if not df.empty:
                df = df.dropna(subset=['Close', 'Open', 'High', 'Low'])
            
            if df.empty or len(df) < 60:
                st.error(f"找不到代號 {stock_code} 的資料或歷史資料不足（需至少 60 交易日），請檢查代號是否正確。")
            else:
                # 計算技術指標與價格數據
                df['MA20'] = df['Close'].rolling(window=20).mean()
                df['MA60'] = df['Close'].rolling(window=60).mean()
                
                std20 = df['Close'].rolling(window=20).std()
                df['BB_Upper'] = df['MA20'] + (std20 * 2)
                df['BB_Lower'] = df['MA20'] - (std20 * 2)

                # RSI 計算
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                df['RSI'] = 100 - (100 / (1 + rs))

                actual_days = min(int(backtest_days), len(df))
                df_plot = df.tail(actual_days).copy()

                # 最新價格與均價統計
                latest_close = df_plot['Close'].iloc[-1]
                latest_high = df_plot['High'].iloc[-1]
                latest_low = df_plot['Low'].iloc[-1]
                period_avg_price = df_plot['Close'].mean()

                # 顯示收盤價、最高價、最低價及均價
                st.subheader("📊 價格與均價資訊摘要")
                p_col1, p_col2, p_col3, p_col4 = st.columns(4)
                p_col1.metric("最新收盤價", f"{latest_close:.2f} 元")
                p_col2.metric("最新最高價", f"{latest_high:.2f} 元")
                p_col3.metric("最新最低價", f"{latest_low:.2f} 元")
                p_col4.metric(f"所選區間均價 ({actual_days}日)", f"{period_avg_price:.2f} 元")

                # 如果是 ETF，顯示折溢價資訊
                if is_etf:
                    st.subheader("🏷️ ETF 官方淨值與折溢價即時評估")
                    
                    api_nav = fetch_etf_nav_api(clean_stock_code)
                    if api_nav:
                        st.success(f"🔗 已成功透過證交所官方 API 自動取得最新淨值 (NAV): {api_nav:.2f} 元")
                        default_nav = api_nav
                    else:
                        st.info("💡 官方 API 目前暫無該 ETF 即時淨值回傳（或非盤中時段），已預設為最新收盤價，您可手動微調。")
                        default_nav = latest_close

                    etf_col1, etf_col2 = st.columns(2)
                    with etf_col1:
                        nav_input = st.number_input("ETF 當前淨值 (NAV) [可手動微調]", min_value=0.0, value=float(default_nav), step=0.05)
                    with etf_col2:
                        if nav_input > 0:
                            premium_discount_pct = ((latest_close - nav_input) / nav_input) * 100
                            pct_str = f"{premium_discount_pct:+.2f}%"
                            if premium_discount_pct > 0:
                                st.metric("折溢價率", pct_str, delta=pct_str, delta_color="inverse")
                                st.warning("⚠️ 目前處於【溢價】狀態（市價高於淨值），買進需注意溢價收斂風險。")
                            elif premium_discount_pct < 0:
                                st.metric("折溢價率", pct_str, delta=pct_str, delta_color="normal")
                                st.success("✅ 目前處於【折價】狀態（市價低於淨值）。")
                            else:
                                st.metric("折溢價率", "+0.00%")
                        else:
                            st.warning("請輸入有效淨值以計算折溢價。")
                else:
                    # 一般股票顯示基本面與財報 (單位：億元)
                    st.subheader("📊 基本面與最新財報摘要")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("本益比 (P/E)", f"{manual_pe:.2f}")
                    with col2:
                        st.metric("股息殖利率", f"{manual_yield:.2f}%")

                    if manual_pe < 15 and manual_yield > 4.0:
                        st.success("✅ 基本面良好：本益比低於 15 且殖利率高於 4%")
                    else:
                        st.info("ℹ️ 目前數值未同時滿足「本益比 < 15 且殖利率 > 4%」之條件")

                    # 顯示近幾季財報數據表 (轉為億元)
                    try:
                        q_financials = ticker.quarterly_financials
                        if not q_financials.empty:
                            st.markdown("##### 📋 近四季財務重點摘要 (單位：億元)")
                            key_rows = []
                            for row_name in ['Total Revenue', 'Gross Profit', 'Net Income']:
                                if row_name in q_financials.index:
                                    key_rows.append(row_name)
                            
                            if key_rows:
                                sub_df = q_financials.loc[key_rows].copy()
                                sub_df = (sub_df / 100000000).round(2)
                                sub_df.columns = [str(col).split()[0] for col in sub_df.columns]
                                st.dataframe(sub_df, use_container_width=True)
                            else:
                                st.info("目前該股票暫無詳細季報明細科目。")
                        else:
                            st.info("目前無可用的季度財報資料。")
                    except Exception:
                        st.info("季報資料載入中或格式不支援。")

                # 買入邏輯：股價由下往上突破布林下軌 (觸底反彈)
                df_plot['Buy_Signal'] = (
                    (df_plot['Close'] > df_plot['BB_Lower']) & 
                    (df_plot['Close'].shift(1) <= df_plot['BB_Lower'].shift(1))
                )
                
                # 賣出邏輯過濾選擇
                if "1. 精準波段" in sell_strategy:
                    df_plot['Sell_Signal'] = (
                        (df_plot['Close'] >= df_plot['BB_Upper']) | 
                        (df_plot['RSI'] >= 75)
                    )
                elif "2. 趨勢防守" in sell_strategy:
                    df_plot['Sell_Signal'] = (
                        (df_plot['Close'] >= df_plot['BB_Upper']) | 
                        ((df_plot['Close'] < df_plot['MA60']) & (df_plot['Close'].shift(1) >= df_plot['MA60'].shift(1)))
                    )
                else:
                    df_plot['Sell_Signal'] = (df_plot['Close'] >= df_plot['BB_Upper'])

                # 回測績效
                st.subheader("🎯 布林通道策略回測績效")
                
                trades = []
                position = False
                buy_price = 0.0

                for date, row in df_plot.iterrows():
                    if not position and row['Buy_Signal']:
                        position = True
                        buy_price = row['Close']
                    elif position and row['Sell_Signal']:
                        position = False
                        sell_price = row['Close']
                        ret = (sell_price - buy_price) / buy_price
                        trades.append(ret)

                total_trades = len(trades)
                if total_trades > 0:
                    win_trades = [r for r in trades if r > 0]
                    win_rate = (len(win_trades) / total_trades) * 100
                    cum_return = (np.prod([1 + r for r in trades]) - 1) * 100
                    
                    p_c1, p_c2, p_c3 = st.columns(3)
                    p_c1.metric("回測總交易次數", f"{total_trades} 次")
                    p_c2.metric("策略勝率", f"{win_rate:.1f}%")
                    p_c3.metric("策略累積總報酬率", f"{cum_return:.2f}%", delta=f"{cum_return:.2f}%")
                else:
                    st.warning("⚠️ 在設定的回測區間內，未觸發完整的「買入→賣出」交易對，無法計算績效數據。")

                # 圖表繪製：K線、布林通道與買賣點
                st.subheader(f"📈 {chinese_name} ({clean_stock_code}) 技術走勢與買賣點")

                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.75, 0.25])

                # K線
                fig.add_trace(go.Candlestick(
                    x=df_plot.index,
                    open=df_plot['Open'], high=df_plot['High'],
                    low=df_plot['Low'], close=df_plot['Close'],
                    name='K線'
                ), row=1, col=1)

                # 均線與布林通道
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA20'], line=dict(color='#FFA500', width=1.5), name='20MA (中軌)'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA60'], line=dict(color='#1E90FF', width=1.5), name='60MA (季線)'), row=1, col=1)
                
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Upper'], line=dict(color='rgba(173, 216, 230, 0.7)', width=1, dash='dot'), name='布林上軌 (+2σ)'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Lower'], line=dict(color='rgba(173, 216, 230, 0.7)', width=1, dash='dot'), fill='tonexty', fillcolor='rgba(173, 216, 230, 0.15)', name='布林下軌 (-2σ)'), row=1, col=1)

                # 買賣點標記
                buy_points = df_plot[df_plot['Buy_Signal']]
                fig.add_trace(go.Scatter(
                    x=buy_points.index, y=buy_points['Low'] * 0.98,
                    mode='markers', marker=dict(symbol='triangle-up', size=14, color='green'),
                    name='觸底買入訊號'
                ), row=1, col=1)

                sell_points = df_plot[df_plot['Sell_Signal']]
                fig.add_trace(go.Scatter(
                    x=sell_points.index, y=sell_points['High'] * 1.02,
                    mode='markers', marker=dict(symbol='triangle-down', size=14, color='red'),
                    name='賣出訊號'
                ), row=1, col=1)

                # 下方附圖：成交量與5日均量
                df_plot['Vol_MA5'] = df_plot['Volume'].rolling(window=5).mean()
                fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], name='成交量', marker_color='gray'), row=2, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Vol_MA5'], name='5日均量', line=dict(color='blue', width=1.2)), row=2, col=1)

                fig.update_layout(
                    title=f"{chinese_name} ({clean_stock_code}) 走勢與優化買賣訊號圖表",
                    height=680,
                    xaxis_rangeslider_visible=False,
                    template="plotly_white"
                )

                st.plotly_chart(fig, use_container_width=True)

                # 籌碼與量能觀察 (顯示最新單日成交量與 5 日均量，單位：萬張)
                st.subheader("🏦 籌碼與量能動能觀察")
                
                c1, c2 = st.columns(2)
                with c1:
                    latest_vol = df_plot['Volume'].iloc[-1]
                    latest_vol_wanzhang = latest_vol / 10000000  # 1萬張 = 1,000,000 股
                    st.metric("最新單日成交量", f"{latest_vol_wanzhang:,.2f} 萬張")
                with c2:
                    latest_vol_ma5 = df_plot['Vol_MA5'].iloc[-1]
                    latest_vol_ma5_wanzhang = latest_vol_ma5 / 10000000
                    st.metric("5日均量", f"{latest_vol_ma5_wanzhang:,.2f} 萬張")

        except Exception as e:
            st.error(f"資料抓取或分析時發生錯誤：{e}")
