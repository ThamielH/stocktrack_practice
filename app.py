import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import twstock

# 設定網頁版面
st.set_page_config(page_title="台股進階全方位分析工具", layout="wide")

st.title("📈 台股進階全方位分析網頁工具")
st.markdown("基本面季報 + 技術面 (含布林通道) + 量能籌碼觀察 + 訊號回測績效評估")

# 1. 初始化網頁端的動態自選股清單
if 'custom_watchlist' not in st.session_state:
    st.session_state.custom_watchlist = {
        "台積電 (2330)": "2330",
        "鴻海 (2317)": "2317",
        "聯發科 (2454)": "2454",
        "台達電 (2308)": "2308",
        "富邦金 (2881)": "2881",
        "廣達 (2382)": "2382"
    }

st.sidebar.header("⭐ 自選股與快速切換")

with st.sidebar.expander("➕ 新增自選股"):
    new_name = st.text_input("股票名稱 (例: 聯詠)", value="", placeholder="可填寫公司名稱")
    new_code = st.text_input("台股代號 (例: 3034)", value="", placeholder="輸入數字代號")
    if st.button("確認加入"):
        if new_code.strip():
            code_clean = new_code.strip().upper().replace(".TW", "").replace(".TWO", "")
            # 自動透過 twstock 補上中文名稱
            auto_name = twstock.codes[code_clean].name if code_clean in twstock.codes else new_name.strip()
            label = f"{auto_name} ({code_clean})"
            st.session_state.custom_watchlist[label] = code_clean
            st.success(f"已成功新增 {label}！")
            st.rerun()
        else:
            st.warning("請至少輸入股票代號！")

st.sidebar.markdown("---")

selected_stock = st.sidebar.radio("點擊直接切換股票：", list(st.session_state.custom_watchlist.keys()), index=0)
default_ticker = st.session_state.custom_watchlist[selected_stock]

st.sidebar.markdown("---")
st.sidebar.header("🔍 手動輸入與回測設定")
stock_input = st.sidebar.text_input("直接輸入其他代號 (例: 2330)", value=default_ticker)
backtest_days = st.sidebar.slider("顯示/回測天數", min_value=30, max_value=730, value=250)

# 清理代號格式並自動加上 .TW
clean_stock_code = stock_input.strip().upper().replace(".TW", "").replace(".TWO", "")
stock_code = clean_stock_code + ".TW"

if clean_stock_code:
    with st.spinner(f"正在分析代號 {clean_stock_code} 中，請稍候..."):
        try:
            ticker = yf.Ticker(stock_code)
            
            # 取得精準的中文名稱 (透過 twstock)
            if clean_stock_code in twstock.codes:
                chinese_name = twstock.codes[clean_stock_code].name
            else:
                chinese_name = clean_stock_code # 若找不到則顯示代號

            st.header(f"📌 當前分析目標：{chinese_name} ({clean_stock_code})")

            fetch_period = "2y" if backtest_days > 250 else "1y"
            df = ticker.history(period=fetch_period)
            
            if df.empty or len(df) < 60:
                st.error(f"找不到代號 {stock_code} 的資料或歷史資料不足（需至少 60 交易日），請檢查代號是否正確。")
            else:
                info = ticker.info

                # 基本面：抓取季報表 (財務數據)
                st.subheader("📊 基本面與最新財報摘要")
                
                pe_ratio = info.get('trailingPE', info.get('forwardPE', None))
                dividend_yield = info.get('dividendYield', None)
                dividend_yield_pct = dividend_yield * 100 if dividend_yield is not None else None

                col1, col2 = st.columns(2)
                with col1:
                    pe_str = f"{pe_ratio:.2f}" if isinstance(pe_ratio, (int, float)) else "N/A"
                    st.metric("本益比 (P/E)", pe_str)
                with col2:
                    yield_str = f"{dividend_yield_pct:.2f}%" if isinstance(dividend_yield_pct, (int, float)) else "N/A"
                    st.metric("股息殖利率", yield_str)

                # 顯示近幾季財報數據表
                try:
                    q_financials = ticker.quarterly_financials
                    if not q_financials.empty:
                        st.markdown("##### 📋 近四季財務重點摘要 (單位：元)")
                        # 選出常見的關鍵科目呈現在表格中
                        key_rows = []
                        for row_name in ['Total Revenue', 'Gross Profit', 'Net Income']:
                            if row_name in q_financials.index:
                                key_rows.append(row_name)
                        
                        if key_rows:
                            sub_df = q_financials.loc[key_rows].copy()
                            # 將欄位名稱轉成字串日期
                            sub_df.columns = [str(col).split()[0] for col in sub_df.columns]
                            st.dataframe(sub_df, use_container_width=True)
                        else:
                            st.info("目前該股票暫無詳細季報明細科目。")
                    else:
                        st.info("目前無可用的季度財報資料。")
                except Exception:
                    st.info("季報資料載入中或格式不支援。")

                # 技術指標計算 (MA, 布林通道, RSI)
                df['MA20'] = df['Close'].rolling(window=20).mean()
                df['MA60'] = df['Close'].rolling(window=60).mean()
                
                std20 = df['Close'].rolling(window=20).std()
                df['BB_Upper'] = df['MA20'] + (std20 * 2)
                df['BB_Lower'] = df['MA20'] - (std20 * 2)

                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                df['RSI'] = 100 - (100 / (1 + rs))

                df_plot = df.tail(backtest_days).copy()

                df_plot['Buy_Signal'] = (
                    (df_plot['Close'] > df_plot['MA20']) & 
                    (df_plot['Close'].shift(1) <= df_plot['MA20'].shift(1)) & 
                    (df_plot['RSI'] < 40)
                )
                
                df_plot['Sell_Signal'] = (
                    ((df_plot['Close'] < df_plot['MA20']) & (df_plot['Close'].shift(1) >= df_plot['MA20'].shift(1))) | 
                    (df_plot['RSI'] > 80)
                )

                # 回測績效
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

                # 圖表
                st.subheader(f"📈 {chinese_name} ({clean_stock_code}) 技術面走勢圖 (含布林通道)")

                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.75, 0.25])

                fig.add_trace(go.Candlestick(
                    x=df_plot.index,
                    open=df_plot['Open'], high=df_plot['High'],
                    low=df_plot['Low'], close=df_plot['Close'],
                    name='K線'
                ), row=1, col=1)

                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA20'], line=dict(color='#FFA500', width=1.5), name='20MA (中軌)'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA60'], line=dict(color='#1E90FF', width=1.5), name='60MA (季線)'), row=1, col=1)
                
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Upper'], line=dict(color='rgba(173, 216, 230, 0.7)', width=1, dash='dot'), name='布林上軌 (+2σ)'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Lower'], line=dict(color='rgba(173, 216, 230, 0.7)', width=1, dash='dot'), fill='tonexty', fillcolor='rgba(173, 216, 230, 0.15)', name='布林下軌 (-2σ)'), row=1, col=1)

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

                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['RSI'], line=dict(color='purple', width=1.5), name='RSI (14)'), row=2, col=1)
                fig.add_hline(y=80, line_dash="solid", line_color="red", row=2, col=1)
                fig.add_hline(y=40, line_dash="solid", line_color="green", row=2, col=1)

                fig.update_layout(
                    title=f"{chinese_name} ({clean_stock_code}) 走勢與買賣點標記",
                    height=650,
                    xaxis_rangeslider_visible=False,
                    template="plotly_white"
                )

                st.plotly_chart(fig, use_container_width=True)

                # 籌碼與量能觀察
                st.subheader("🏦 籌碼與量能動能觀察")
                st.info("💡 說明：此處展示市場成交量與 5 日均量，作為評估大戶/法人資金活躍度與流動性的重要指標。")

                df_plot['Vol_MA5'] = df_plot['Volume'].rolling(window=5).mean()
                
                c1, c2 = st.columns(2)
                with c1:
                    latest_vol = df_plot['Volume'].iloc[-1]
                    st.metric("最新單日成交量", f"{latest_vol:,.0f} 股")
                with c2:
                    latest_vol_ma5 = df_plot['Vol_MA5'].iloc[-1]
                    st.metric("5日均量", f"{latest_vol_ma5:,.0f} 股")

                fig_vol = go.Figure()
                fig_vol.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], name='每日成交量', marker_color='gray'))
                fig_vol.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Vol_MA5'], name='5日均量', line=dict(color='blue', width=1.5)))
                fig_vol.update_layout(title="成交量與 5 日均量趨勢", height=280, template="plotly_white")
                st.plotly_chart(fig_vol, use_container_width=True)

        except Exception as e:
            st.error(f"資料抓取或分析時發生錯誤：{e}")
