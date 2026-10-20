import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# 設定網頁版面
st.set_page_config(page_title="台股基本面與技術面分析工具", layout="wide")

st.title("📈 台股基本面與技術面分析網頁工具")
st.markdown("輸入台股代號與回測天數，一鍵為您評估基本面並標註技術面買賣點！")

# 側邊欄輸入設定
st.sidebar.header("🔍 查詢設定")
stock_input = st.sidebar.text_input("輸入台股代號 (例如 2330)", value="2330")
backtest_days = st.sidebar.slider("顯示/回測天數", min_value=30, max_value=730, value=250)

# 自動補上 .TW
stock_code = stock_input.strip().upper()
if not stock_code.endswith(".TW") and not stock_code.endswith(".TWO"):
    stock_code += ".TW"

if st.sidebar.button("開始分析", type="primary"):
    with st.spinner(f"正在抓取 {stock_code} 的財報與股價資料..."):
        try:
            ticker = yf.Ticker(stock_code)
            
            # 抓取歷史股價資料 (抓兩年以確保 60MA 與 RSI 計算充足)
            fetch_period = "2y" if backtest_days > 250 else "1y"
            df = ticker.history(period=fetch_period)
            
            if df.empty or len(df) < 60:
                st.error(f"找不到代號 {stock_code} 的資料或歷史資料不足（需至少 60 交易日），請檢查代號是否正確。")
            else:
                # 1. 基本面數據取得
                info = ticker.info
                pe_ratio = info.get('trailingPE', info.get('forwardPE', 'N/A'))
                
                dividend_yield = info.get('dividendYield', None)
                dividend_yield_pct = dividend_yield * 100 if dividend_yield is not None else None

                # 最新季度營收狀況
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

                # 基本面判定條件：本益比 < 15 且殖利率 > 4%
                is_pe_good = isinstance(pe_ratio, (int, float)) and pe_ratio < 15
                is_yield_good = isinstance(dividend_yield_pct, (int, float)) and dividend_yield_pct > 4.0
                
                if is_pe_good and is_yield_good:
                    st.success("✅ 基本面良好：本益比低於 15 且殖利率高於 4%")
                else:
                    st.info("ℹ️ 該股票目前未同時滿足「本益比 < 15 且殖利率 > 4%」之條件")

                # 2. 技術指標計算 (20MA, 60MA, RSI)
                df['MA20'] = df['Close'].rolling(window=20).mean()
                df['MA60'] = df['Close'].rolling(window=60).mean()
                
                # 計算 14 日 RSI
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                df['RSI'] = 100 - (100 / (1 + rs))

                # 截取使用者指定的天數範圍
                df_plot = df.tail(backtest_days).copy()

                # 3. 買賣訊號判斷
                # 買入訊號：股價突破 20MA 且 RSI < 40
                df_plot['Buy_Signal'] = (
                    (df_plot['Close'] > df_plot['MA20']) & 
                    (df_plot['Close'].shift(1) <= df_plot['MA20'].shift(1)) & 
                    (df_plot['RSI'] < 40)
                )
                
                # 賣出訊號：股價跌破 20MA 或 RSI > 80
                df_plot['Sell_Signal'] = (
                    ((df_plot['Close'] < df_plot['MA20']) & (df_plot['Close'].shift(1) >= df_plot['MA20'].shift(1))) | 
                    (df_plot['RSI'] > 80)
                )

                st.subheader("📈 技術面走勢與買賣點標記")
                
                # 繪製主圖：K線與均線、買賣點
                fig = go.Figure()

                # K線圖
                fig.add_trace(go.Candlestick(
                    x=df_plot.index,
                    open=df_plot['Open'],
                    high=df_plot['High'],
                    low=df_plot['Low'],
                    close=df_plot['Close'],
                    name='K線'
                ))

                # 月線與季線
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA20'], line=dict(color='#FFA500', width=1.5), name='20MA (月線)'))
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA60'], line=dict(color='#1E90FF', width=1.5), name='60MA (季線)'))

                # 買入點標記（綠色向上三角形）
                buy_points = df_plot[df_plot['Buy_Signal']]
                fig.add_trace(go.Scatter(
                    x=buy_points.index,
                    y=buy_points['Low'] * 0.98,
                    mode='markers',
                    marker=dict(symbol='triangle-up', size=14, color='green'),
                    name='買入訊號'
                ))

                # 賣出點標記（紅色向下三角形）
                sell_points = df_plot[df_plot['Sell_Signal']]
                fig.add_trace(go.Scatter(
                    x=sell_points.index,
                    y=sell_points['High'] * 1.02,
                    mode='markers',
                    marker=dict(symbol='triangle-down', size=14, color='red'),
                    name='賣出訊號'
                ))

                fig.update_layout(
                    title=f"{stock_code} 股價走勢與進出點標記",
                    xaxis_title="日期",
                    yaxis_title="價格 (TWD)",
                    xaxis_rangeslider_visible=False,
                    height=550,
                    template="plotly_white"
                )

                st.plotly_chart(fig, use_container_width=True)

                # 繪製 RSI 指標附圖
                fig_rsi = go.Figure()
                fig_rsi.add_trace(go.Scatter(x=df_plot.index, y=df_plot['RSI'], line=dict(color='purple', width=1.5), name='RSI (14)'))
                fig_rsi.add_hline(y=80, line_dash="solid", line_color="red", annotation_text="超買警戒線 (80)")
                fig_rsi.add_hline(y=40, line_dash="solid", line_color="green", annotation_text="超賣警戒線 (40)")
                
                fig_rsi.update_layout(
                    title=f"{stock_code} RSI 動能指標",
                    xaxis_title="日期",
                    yaxis_title="RSI",
                    height=280,
                    template="plotly_white"
                )
                st.plotly_chart(fig_rsi, use_container_width=True)

        except Exception as e:
            st.error(f"分析過程中發生錯誤：{e}")
            
