import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
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
        ["시가총액 상위 50종목 (초고속)", "시가총액 상위 100종목 (빠름)", "시가총액 상위 200종목 (권장)"]
    )
    
    period = st.number_input("볼린저 밴드 기간 (기본: 20)", min_value=5, max_value=60, value=20)
    dev_multiplier = st.number_input("표준편차 배수 (기본: 2.0)", min_value=1.0, max_value=3.0, value=2.0, step=0.1)
    
    run_btn = st.button("🚀 종목 스캔 시작", type="primary", use_container_width=True)

# ── 1. 네이버 금융에서 코스피 시총 상위 종목 수집 (해외 IP 차단 우회) ──
@st.cache_data(ttl=3600)
def get_kospi_top_list(target_count):
    headers = {'User-Agent': 'Mozilla/5.0'}
    stocks = []
    
    pages = (target_count // 50) + 1
    for page in range(1, pages + 1):
        url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page={page}"
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        table = soup.find('table', {'class': 'type_2'})
        if not table:
            continue
            
        for a in table.find_all('a', {'class': 'tltle'}):
            name = a.text.strip()
            # 우선주 제외
            if name.endswith(('우', '우B', '우C')):
                continue
            code = a['href'].split('code=')[-1]
            stocks.append({'Code': code, 'Name': name})
            
            if len(stocks) >= target_count:
                break
        if len(stocks) >= target_count:
            break
            
    return pd.DataFrame(stocks)

# ── 2. 볼린저 밴드 스캔 함수 ──
def scan_bollinger_breakout(df_target, period, dev):
    start_date = (datetime.today() - timedelta(days=120)).strftime('%Y-%m-%d')
    total = len(df_target)
    
    breakout_list = []      # 당일 갓 돌파
    above_band_list = []    # 상한선 위에 위치
    
    prog_bar = st.progress(0, text="종목 데이터 수집 및 계산 시작...")
    
    for i, (_, row) in enumerate(df_target.iterrows()):
        ticker = row['Code']
        name = row['Name']
        
        prog_bar.progress((i + 1) / total, text=f"분석 중 ({i+1}/{total}): {name} ({ticker})")
        
        try:
            df = fdr.DataReader(ticker, start=start_date)
            if len(df) < period + 5:
                continue
                
            # 볼린저 밴드 계산
            df['MA'] = df['Close'].rolling(window=period).mean()
            df['STD'] = df['Close'].rolling(window=period).std()
            df['Upper'] = df['MA'] + (df['STD'] * dev)
            
            prev_close, prev_upper = df['Close'].iloc[-2], df['Upper'].iloc[-2]
            curr_close, curr_upper = df['Close'].iloc[-1], df['Upper'].iloc[-1]
            
            change_rate = ((curr_close / prev_close) - 1) * 100
            pct_over_upper = ((curr_close / curr_upper) - 1) * 100
            
            stock_info = {
                '종목코드': ticker,
                '종목명': name,
                '현재가': f"{int(curr_close):,}원",
                '상한선': f"{round(curr_upper, 1):,}원",
                '상한선초과율': f"+{pct_over_upper:.2f}%",
                '전일대비등락률': f"{change_rate:+.2f}%"
            }
            
            # 상단선 위에 있는 경우
            if curr_close > curr_upper:
                above_band_list.append(stock_info)
                # 당일 갓 돌파한 경우
                if prev_close <= prev_upper:
                    breakout_list.append(stock_info)
                    
        except Exception:
            continue
            
    prog_bar.empty()
    return pd.DataFrame(breakout_list), pd.DataFrame(above_band_list)

# ── 3. 실행 UI ──
if run_btn:
    count_map = {
        "시가총액 상위 50종목 (초고속)": 50,
        "시가총액 상위 100종목 (빠름)": 100,
        "시가총액 상위 200종목 (권장)": 200
    }
    target_count = count_map.get(scan_scope, 100)
    
    with st.spinner("코스피 시가총액 상위 종목 목록을 수집 중입니다..."):
        target_df = get_kospi_top_list(target_count)
        
    st.info(f"총 **{len(target_df)}개** 종목을 대상으로 볼린저 밴드 분석을 시작합니다.")
    df_breakout, df_above = scan_bollinger_breakout(target_df, period, dev_multiplier)
    
    st.subheader("📊 스캔 결과 요약")
    col1, col2, col3 = st.columns(3)
    col1.metric("총 분석 종목", f"{len(target_df)}개")
    col2.metric("당일 갓 상향돌파 종목", f"{len(df_breakout)}개")
    col3.metric("상한선 초과 종목 (전체)", f"{len(df_above)}개")
    
    tab1, tab2 = st.tabs(["🚀 당일 갓 상향돌파 종목", "📈 상한선 초과 유지 종목"])
    
    with tab1:
        st.caption("어제까지 상한선 밑에 머물다가 오늘 밴드 상단을 뚫고 올라온 종목입니다.")
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
