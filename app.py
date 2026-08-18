import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="코스피 볼린저 밴드 스캐너", page_icon="🔍", layout="wide")

st.title("🔍 코스피 볼린저 밴드 상단 돌파 스캐너")
st.markdown("""
코스피 종목의 일봉 데이터를 분석하여 **볼린저 밴드(20, 2) 상단선을 돌파한 종목**을 실시간으로 탐색합니다.
* **당일 돌파:** 전일에는 상단선 아래에 있다가 당일 갓 상단을 뚫고 올라온 종목 (골든크로스)
* **상단 초과 유지:** 현재 종가가 상한선 위에 위치하고 있는 모든 종목
""")

# ── 사이드바 설정 ──
with st.sidebar:
    st.header("⚙️ 스캔 옵션")
    scan_scope = st.selectbox(
        "스캔 대상 범위",
        ["시가총액 상위 100종목 (빠름)", "시가총액 상위 200종목 (권장)", "코스피 전체 종목 (약 2~3분 소요)"]
    )
    
    period = st.number_input("볼린저 밴드 기간 (기본: 20)", min_value=5, max_value=60, value=20)
    dev_multiplier = st.number_input("표준편차 배수 (기본: 2.0)", min_value=1.0, max_value=3.0, value=2.0, step=0.1)
    
    run_btn = st.button("🚀 종목 스캔 시작", type="primary", use_container_width=True)

# ── 볼린저 밴드 스캔 함수 ──
def scan_bollinger_breakout(df_target, period, dev):
    start_date = (datetime.today() - timedelta(days=120)).strftime('%Y-%m-%d')
    total = len(df_target)
    
    breakout_list = []      # 당일 갓 돌파
    above_band_list = []    # 상한선 위에 위치
    
    prog_bar = st.progress(0, text="종목 데이터 수집 및 계산 시작...")
    
    for i, (_, row) in enumerate(df_target.iterrows()):
        ticker = row['Code']
        name = row['Name']
        
        # 진행률 업데이트
        prog_bar.progress((i + 1) / total, text=f"분석 중 ({i+1}/{total}): {name} ({ticker})")
        
        try:
            df = fdr.DataReader(ticker, start=start_date)
            if len(df) < period + 5:
                continue
                
            # 볼린저 밴드 계산
            df['MA'] = df['Close'].rolling(window=period).mean()
            df['STD'] = df['Close'].rolling(window=period).std()
            df['Upper'] = df['MA'] + (df['STD'] * dev)
            
            # 최근 2개 거래일 종가 및 상한선
            prev_close, prev_upper = df['Close'].iloc[-2], df['Upper'].iloc[-2]
            curr_close, curr_upper = df['Close'].iloc[-1], df['Upper'].iloc[-1]
            
            # 1일 전 대비 등락률
            change_rate = ((curr_close / prev_close) - 1) * 100
            pct_over_upper = ((curr_close / curr_upper) - 1) * 100
            
            stock_info = {
                '종목코드': ticker,
                '종목명': name,
                '현재가': int(curr_close),
                '상한선': round(curr_upper, 1),
                '상한선초과율': f"+{pct_over_upper:.2f}%",
                '전일대비등락률': f"{change_rate:+.2f}%"
            }
            
            # 상단 위에 있는 종목
            if curr_close > curr_upper:
                above_band_list.append(stock_info)
                
                # 어제는 상단 아래였으나 오늘 갓 뚫은 경우
                if prev_close <= prev_upper:
                    breakout_list.append(stock_info)
                    
        except Exception:
            continue
            
    prog_bar.empty()
    return pd.DataFrame(breakout_list), pd.DataFrame(above_band_list)

# ── 실행 로직 ──
if run_btn:
    with st.spinner("코스피 종목 목록을 불러오는 중입니다..."):
        kospi_df = fdr.StockListing('KOSPI')
        # 우선주 및 스팩주 제외
        kospi_df = kospi_df[~kospi_df['Name'].str.endswith(('우', '우B', '우C'))].copy()
        
        # 시가총액 기준 정렬
        if 'MarCap' in kospi_df.columns:
            kospi_df = kospi_df.sort_values(by='MarCap', ascending=False)
            
        if "100종목" in scan_scope:
            target_df = kospi_df.head(100)
        elif "200종목" in scan_scope:
            target_df = kospi_df.head(200)
        else:
            target_df = kospi_df
            
    st.info(f"총 **{len(target_df)}개** 종목을 대상으로 분석을 시작합니다.")
    df_breakout, df_above = scan_bollinger_breakout(target_df, period, dev_multiplier)
    
    # ── 요약 메트릭 ──
    st.subheader("📊 스캔 결과 요약")
    col1, col2, col3 = st.columns(3)
    col1.metric("총 분석 종목", f"{len(target_df)}개")
    col2.metric("당일 갓 상향돌파 종목", f"{len(df_breakout)}개")
    col3.metric("상한선 초과 종목 (전체)", f"{len(df_above)}개")
    
    # ── 결과 테이블 ──
    tab1, tab2 = st.tabs(["🚀 당일 갓 상향돌파 종목", "📈 상한선 초과 유지 종목"])
    
    with tab1:
        st.caption("어제까지 상한선 밑에 머물다가 오늘 거래에서 밴드 상단을 뚫고 올라온 종목입니다.")
        if not df_breakout.empty:
            st.dataframe(df_breakout.reset_index(drop=True), use_container_width=True)
        else:
            st.warning("조건을 만족하는 당일 돌파 종목이 없습니다.")
            
    with tab2:
        st.caption("현재 종가가 볼린저 밴드 상한선보다 위에 위치해 있는 모든 종목입니다.")
        if not df_above.empty:
            st.dataframe(df_above.reset_index(drop=True), use_container_width=True)
        else:
            st.warning("상한선 위에 위치한 종목이 없습니다.")
