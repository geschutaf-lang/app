import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="기간별 볼린저 밴드 돌파 스캐너", page_icon="📅", layout="wide")

st.title("📅 기간별 코스피 볼린저 밴드 상단 돌파 탐색기")
st.markdown("""
설정한 **시작일 ~ 종료일** 기간 동안 일자별로 **볼린저 밴드(20, 2) 상단선을 갓 돌파한 종목(골든크로스)**을 탐색합니다.
* **돌파 조건:** 전일 종가 $\le$ 전일 상한선 AND 당일 종가 $>$ 당일 상한선
""")

# ── 사이드바 설정 ──
with st.sidebar:
    st.header("⚙️ 분석 조건 설정")
    
    # 분석 기간 선택 (기본값 설정)
    default_end = datetime(2026, 1, 7).date() if datetime.today().year >= 2026 else datetime.today().date()
    default_start = datetime(2026, 1, 3).date() if datetime.today().year >= 2026 else (default_end - timedelta(days=7))
    
    date_range = st.date_input(
        "분석 기간 선택",
        value=(default_start, default_end),
        max_value=datetime.today().date()
    )
    
    scan_scope = st.selectbox(
        "스캔 대상 범위",
        ["시가총액 상위 50종목 (초고속)", "시가총액 상위 100종목 (빠름)", "시가총액 상위 200종목 (권장)"]
    )
    
    period = st.number_input("볼린저 밴드 기간 (기본: 20)", min_value=5, max_value=60, value=20)
    dev_multiplier = st.number_input("표준편차 배수 (기본: 2.0)", min_value=1.0, max_value=3.0, value=2.0, step=0.1)
    
    run_btn = st.button("🚀 기간별 스캔 시작", type="primary", use_container_width=True)

# ── 1. 네이버 금융 시가총액 상위 수집 ──
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
            if name.endswith(('우', '우B', '우C')):
                continue
            code = a['href'].split('code=')[-1]
            stocks.append({'Code': code, 'Name': name})
            
            if len(stocks) >= target_count:
                break
        if len(stocks) >= target_count:
            break
            
    return pd.DataFrame(stocks)

# ── 2. 기간별 볼린저 밴드 돌파 탐색 함수 ──
def scan_period_breakout(df_target, start_dt, end_dt, period, dev):
    # 20일 이동평균 계산을 위해 시작일보다 90일 전부터 데이터 조회
    fetch_start = (start_dt - timedelta(days=90)).strftime('%Y-%m-%d')
    fetch_end = (end_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    
    total = len(df_target)
    all_breakouts = []
    
    prog_bar = st.progress(0, text="데이터 수집 및 기간별 계산 시작...")
    
    for i, (_, row) in enumerate(df_target.iterrows()):
        ticker = row['Code']
        name = row['Name']
        
        prog_bar.progress((i + 1) / total, text=f"분석 중 ({i+1}/{total}): {name} ({ticker})")
        
        try:
            df = fdr.DataReader(ticker, start=fetch_start, end=fetch_end)
            if len(df) < period + 5:
                continue
                
            # 볼린저 밴드 계산
            df['MA'] = df['Close'].rolling(window=period).mean()
            df['STD'] = df['Close'].rolling(window=period).std()
            df['Upper'] = df['MA'] + (df['STD'] * dev)
            
            # 사용자 지정 기간 필터링
            target_mask = (df.index.date >= start_dt) & (df.index.date <= end_dt)
            target_dates = df.index[target_mask]
            
            for dt in target_dates:
                idx_pos = df.index.get_loc(dt)
                if idx_pos == 0:
                    continue
                
                prev_close = df['Close'].iloc[idx_pos - 1]
                prev_upper = df['Upper'].iloc[idx_pos - 1]
                curr_close = df['Close'].iloc[idx_pos]
                curr_upper = df['Upper'].iloc[idx_pos]
                
                # 당일 상향 돌파 조건 체크
                if prev_close <= prev_upper and curr_close > curr_upper:
                    change_rate = ((curr_close / prev_close) - 1) * 100
                    pct_over_upper = ((curr_close / curr_upper) - 1) * 100
                    
                    all_breakouts.append({
                        '돌파 날짜': dt.strftime('%Y-%m-%d'),
                        '종목코드': ticker,
                        '종목명': name,
                        '당일 종가': f"{int(curr_close):,}원",
                        '상한선': f"{round(curr_upper, 1):,}원",
                        '상한선 초과율': f"+{pct_over_upper:.2f}%",
                        '당일 등락률': f"{change_rate:+.2f}%"
                    })
        except Exception:
            continue
            
    prog_bar.empty()
    return pd.DataFrame(all_breakouts)

# ── 3. 실행 및 결과 표시 ──
if run_btn:
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        st.error("시작일과 종료일을 모두 선택해 주세요.")
        st.stop()
        
    if start_date > end_date:
        st.error("시작일은 종료일보다 이전이어야 합니다.")
        st.stop()

    count_map = {
        "시가총액 상위 50종목 (초고속)": 50,
        "시가총액 상위 100종목 (빠름)": 100,
        "시가총액 상위 200종목 (권장)": 200
    }
    target_count = count_map.get(scan_scope, 100)
    
    with st.spinner("코스피 종목 목록 수집 중..."):
        target_df = get_kospi_top_list(target_count)
        
    st.info(f"분석 대상: **{len(target_df)}개 종목** | 분석 기간: **{start_date} ~ {end_date}**")
    df_results = scan_period_breakout(target_df, start_date, end_date, period, dev_multiplier)
    
    # ── 결과 요약 메트릭 ──
    st.subheader("📊 스캔 결과 요약")
    c1, c2, c3 = st.columns(3)
    c1.metric("분석 기간", f"{(end_date - start_date).days + 1}일간")
    c2.metric("총 돌파 이벤트 건수", f"{len(df_results)}건")
    c3.metric("돌파 종목 수 (중복 제외)", f"{df_results['종목코드'].nunique() if not df_results.empty else 0}개")
    
    if not df_results.empty:
        # 날짜 내림차순 정렬
        df_results = df_results.sort_values(by=['돌파 날짜', '종목명'], ascending=[False, True]).reset_index(drop=True)
        
        # 탭 분리: 날짜별 모아보기 & 전체 목록 테이블
        tab1, tab2 = st.tabs(["📅 날짜별 그룹 보기", "📋 전체 목록 테이블"])
        
        with tab1:
            unique_dates = df_results['돌파 날짜'].unique()
            for d in sorted(unique_dates, reverse=True):
                sub_df = df_results[df_results['돌파 날짜'] == d].drop(columns=['돌파 날짜']).reset_index(drop=True)
                with st.expander(f"📌 **{d}** 상단 돌파 종목 ({len(sub_df)}개)", expanded=True):
                    st.dataframe(sub_df, use_container_width=True)
                    
        with tab2:
            st.dataframe(df_results, use_container_width=True)
    else:
        st.warning(f"선택하신 기간 ({start_date} ~ {end_date}) 동안 볼린저 밴드 상단을 돌파한 종목이 없습니다.")
