import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 設定網頁版面
st.set_page_config(page_title="台股進階全方位分析工具", layout="wide")

st.title("📈 台股進階全方位分析網頁工具")
st.markdown("基本面 + 技術面 (含布林通道) + 籌碼面觀察 + 訊號回測績效評估")

# 1. 側邊欄：自選股與查詢設定
st.sidebar.header("⭐ 自選股快捷選單")

# 預設熱門自選股字典 (可自訂)
watchlist = {
    "台積電 (2330)": "2330",
    "鴻海 (2317)": "2317",
    "聯發科 (2454)": "2454",
    "台達電 (2308)": "2308",
    "富邦金 (2881)": "2881",
    "廣達 (2382)": "2382"
}

# 自選股點選
selected_stock = st.sidebar.radio("點擊直接切換股票：", list(watchlist.keys()), index=0)
default_ticker = watchlist[selected_stock]

st.sidebar.markdown("---")
st.sidebar.header("🔍 手動輸入與回測設定")
stock_input = st.sidebar.text_input("輸入台股代號 (例: 2330)", value=default_ticker)
backtest_days = st.sidebar.slider("顯示/回測天數", min_value=30, max_value=730, value=250)

# 自動處理台股代號字尾 (.TW / .TWO)
stock_code = stock_input.strip().upper()
if not stock_code.endswith(".TW") and not stock_code.endswith(".TWO"):
    stock_code += ".TW"

# 開始分析按鈕
if st.sidebar.button("開始分析", type="primary") or stock_code:
    with st.spinner(f"正在分析 {stock_code} 中，請稍候..."):
        try:
            ticker = yf.Ticker(stock_code)
            
            # 抓取股價歷史資料
            fetch_period = "2y" if backtest_days > 250 else "1y"
            df = ticker.history(period=fetch_period)
            
            if df.empty or len(df) < 60:
                st.error(f"找不到代號 {stock_code} 的資料或歷史資料不足（需至少 60 交易日），請檢查代號是否正確。")
            else:
                # 2. 獲取股票中文名稱與基本面
                info = ticker.info
                short_name = info.get('shortName', info.get('longName', stock_code))
                
                # 標題顯示中文名稱
                st.header(f"📌 當前分析目標：{short_name} ({stock_code})")

                # 基本面數據
                pe_ratio = info.get('trailingPE', info.get('forwardPE', 'N/A'))
                dividend_yield = info.get('dividendYield', None)
                dividend_yield_pct = dividend_yield * 100 if dividend_yield is not None else None

                try:
                    quarterly_financials = ticker.quarterly_financials
                    if not quarterly_financials.empty and 'Total Revenue' in quarterly_financials.index:
                        latest_rev = quarterly_financials.loc['Total Revenue'].iloc[0]
                    else:
                        latest_rev = "無詳細季報資料"
                except Exception:
                    latest_rev = "無詳細季報資料"

                # 呈現基本面指標
                st.subheader("📊 基本面檢查摘要")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    pe_str = f"{pe_ratio:.2f}" if isinstance(pe_ratio, (int, float)) else str(pe_ratio)
                    st.metric("本益比 (P/E)", pe_str)
                
                with col2:
                    yield_str = f"{dividend_yield_pct:.2f}%" if isinstance(dividend_yield_pct, (int, float)) else "N/A"
                    st.metric("股息殖利率", yield_str)
                    
                with col3:
                    rev_str = f"{latest_rev:,.0f}" if isinstance(latest_rev, (int, float)) else str(latest_rev)
                    st.metric("最新季度營收", rev_str)

                is_pe_good = isinstance(pe_ratio, (int, float)) and pe_ratio < 15
                is_yield_good = isinstance(dividend_yield_pct, (int, float)) and dividend_yield_pct > 4.0
                
                if is_pe_good and is_yield_good:
                    st.success("✅ 基本面良好：本益比低於 15 且殖利率高於 4%")
                else:
                    st.info("ℹ️ 該股票目前未同時滿足「本益比 < 15 且殖利率 > 4%」之條件")

                # 3. 計算技術指標 (MA, 布林通道, RSI)
                df['MA20'] = df['Close'].rolling(window=20).mean()
                df['MA60'] = df['Close'].rolling(window=60).mean()
                
                # 布林通道 (Bollinger Bands: 20日均線 ± 2標準差)
                std20 = df['Close'].rolling(window=20).std()
                df['BB_Upper'] = df['MA20'] + (std20 * 2)
                df['BB_Lower'] = df['MA20'] - (std20 * 2)

                # RSI (14日)
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                df['RSI'] = 100 - (100 / (1 + rs))

                # 裁切回測天數
                df_plot = df.tail(backtest_days).copy()

                # 買賣訊號判定
                df_plot['Buy_Signal'] = (
                    (df_plot['Close'] > df_plot['MA20']) & 
                    (df_plot['Close'].shift(1) <= df_plot['MA20'].shift(1)) & 
                    (df_plot['RSI'] < 40)
                )
                
                df_plot['Sell_Signal'] = (
                    ((df_plot['Close'] < df_plot['MA20']) & (df_plot['Close'].shift(1) >= df_plot['MA20'].shift(1))) | 
                    (df_plot['RSI'] > 80)
                )

                # 4. 回測績效計算
                st.subheader("🎯 技術訊號回測績效評估")
                
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
                    
                    p_col1, p_col2, p_col3 = st.columns(3)
                    p_col1.metric("回測總交易次數", f"{total_trades} 次")
                    p_col2.metric("交易勝率", f"{win_rate:.1f}%")
                    p_col3.metric("策略累積總報酬率", f"{cum_return:.2f}%", delta=f"{cum_return:.2f}%")
                else:
                    st.warning("⚠️ 在設定的回測區間內，未觸發完整的「買入→賣出」交易對，無法計算績效數據。")

                # 5. 圖表繪製：包含 K 線、布林通道、MA、買賣點與 RSI
                st.subheader("📈 技術面走勢圖 (含布林通道與買賣點)")

                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.75, 0.25])

                # K線圖
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
                    name='買入訊號'
                ), row=1, col=1)

                sell_points = df_plot[df_plot['Sell_Signal']]
                fig.add_trace(go.Scatter(
                    x=sell_points.index, y=sell_points['High'] * 1.02,
                    mode='markers', marker=dict(symbol='triangle-down', size=14, color='red'),
                    name='賣出訊號'
                ), row=1, col=1)

                # RSI 圖表
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['RSI'], line=dict(color='purple', width=1.5), name='RSI (14)'), row=2, col=1)
                fig.add_hline(y=80, line_dash="solid", line_color="red", row=2, col=1)
                fig.add_hline(y=40, line_dash="solid", line_color="green", row=2, col=1)

                fig.update_layout(
                    title=f"{short_name} ({stock_code}) 走勢分析與買賣訊號",
                    height=650,
                    xaxis_rangeslider_visible=False,
                    template="plotly_white"
                )

                st.plotly_chart(fig, use_container_width=True)

                # 6. 籌碼面資訊觀察
                st.subheader("🏦 籌碼面觀察 (成交量與機構持股現況)")
                
                c_col1, c_col2 = st.columns(2)
                
                with c_col1:
                    inst_percent = info.get('heldPercentInstitutions', None)
                    inst_str = f"{inst_percent * 100:.2f}%" if isinstance(inst_percent, (int, float)) else "無詳細數據"
                    st.metric("機構/法人持股比例", inst_str)
                    
                    short_ratio = info.get('shortPercentOfFloat', None)
                    short_str = f"{short_ratio * 100:.2f}%" if isinstance(short_ratio, (int, float)) else "無詳細數據"
                    st.metric("做空/融券相關比例", short_str)

                with c_col2:
                    avg_vol = info.get('averageVolume', 'N/A')
                    avg_vol_str = f"{avg_vol:,.0f} 股" if isinstance(avg_vol, (int, float)) else str(avg_vol)
                    st.metric("近 3 個月日均成交量", avg_vol_str)

                # 繪製每日成交量變化圖
                fig_vol = go.Figure()
                fig_vol.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], name='每日成交量', marker_color='gray'))
                fig_vol.update_layout(title="近期的成交量變化趨勢", height=280, template="plotly_white")
                st.plotly_chart(fig_vol, use_container_width=True)

        except Exception as e:
            st.error(f"資料抓取或分析時發生錯誤：{e}")
