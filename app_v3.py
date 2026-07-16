import streamlit as st
import pandas as pd
import numpy as np
import folium
import json
import os
import re
from streamlit_folium import st_folium

st.set_page_config(layout="wide")
st.title("🇮🇩 인도네시아 주별 환경탄력성 지수 시뮬레이터")
st.markdown("가중치를 조절하면 우측 지도의 주별 색상과 좌측 랭킹이 실시간으로 시각화됩니다.")

# 🗺️ 엑셀 주 이름 -> GeoJSON 표준 주 이름(NAME_1) 매핑 딕셔너리
PROVINCE_MAP = {
    # 자카르타 / 요그야카르타
    "dki jakarta": "Jakarta Raya",
    "jakarta": "Jakarta Raya",
    "jakarta raya": "Jakarta Raya",
    "di yogyakarta": "Yogyakarta",
    "yogyakarta": "Yogyakarta",
    
    # 아체 / 방카벨리퉁
    "nanggroe aceh darussalam": "Aceh",
    "aceh": "Aceh",
    "bangka belitung": "Kepulauan Bangka Belitung",
    "kepulauan bangka belitung": "Kepulauan Bangka Belitung",
    "kep. bangka belitung": "Kepulauan Bangka Belitung",
    
    # 수마트라 지역
    "west sumatera": "Sumatera Barat",
    "sumatera barat": "Sumatera Barat",
    "north sumatera": "Sumatera Utara",
    "sumatera utara": "Sumatera Utara",
    "south sumatera": "Sumatera Selatan",
    "sumatera selatan": "Sumatera Selatan",
    "kepulauan riau": "Kepulauan Riau",
    "kep. riau": "Kepulauan Riau",
    
    # 자와 지역
    "west java": "Jawa Barat",
    "jawa barat": "Jawa Barat",
    "east java": "Jawa Timur",
    "jawa timur": "Jawa Timur",
    "central java": "Jawa Tengah",
    "jawa tengah": "Jawa Tengah",
    "banten": "Banten",
    
    # 칼리만탄 지역
    "west kalimantan": "Kalimantan Barat",
    "kalimantan barat": "Kalimantan Barat",
    "east kalimantan": "Kalimantan Timur",
    "kalimantan timur": "Kalimantan Timur",
    "south kalimantan": "Kalimantan Selatan",
    "kalimantan selatan": "Kalimantan Selatan",
    "central kalimantan": "Kalimantan Tengah",
    "kalimantan tengah": "Kalimantan Tengah",
    "north kalimantan": "Kalimantan Utara",
    "kalimantan utara": "Kalimantan Utara",
    
    # 술라웨시 지역
    "west sulawesi": "Sulawesi Barat",
    "sulawesi barat": "Sulawesi Barat",
    "north sulawesi": "Sulawesi Utara",
    "sulawesi utara": "Sulawesi Utara",
    "south sulawesi": "Sulawesi Selatan",
    "sulawesi selatan": "Sulawesi Selatan",
    "central sulawesi": "Sulawesi Tengah",
    "sulawesi tengah": "Sulawesi Tengah",
    "southeast sulawesi": "Sulawesi Tenggara",
    "sulawesi tenggara": "Sulawesi Tenggara",
    "gorontalo": "Gorontalo",
    
    # 누사텡가라 및 말루쿠 지역
    "west nusa tenggara": "Nusa Tenggara Barat",
    "nusa tenggara barat": "Nusa Tenggara Barat",
    "east nusa tenggara": "Nusa Tenggara Timur",
    "nusa tenggara timur": "Nusa Tenggara Timur",
    "maluku": "Maluku",
    "north maluku": "Maluku Utara",
    "maluku utara": "Maluku Utara",
    
    # 파푸아 지역
    "papua": "Papua",
    "west papua": "Papua Barat",
    "papua barat": "Papua Barat"
}

# 주 이름을 깔끔하게 청소하고 지도의 표준 명칭으로 교정하는 함수
def clean_province_name(name):
    if pd.isna(name):
        return ""
    # 줄 바꿈 제거 및 양끝 공백 정리
    name_str = str(name).replace('\n', ' ').strip()
    name_str = re.sub(r'\s+', ' ', name_str)
    
    # 매핑 테이블 매칭 시도 (소문자 기준 검색)
    lookup_key = name_str.lower()
    if lookup_key in PROVINCE_MAP:
        return PROVINCE_MAP[lookup_key]
    
    # 예외적인 한글 공백이나 대소문자 예방을 위한 타이틀화
    return name_str.title()

@st.cache_data
def load_and_match_data():
    # 1. 기온 데이터 로드 (data(최종).xlsx)
    try:
        xls_temp = pd.ExcelFile("data(최종).xlsx")
        df_temp_raw = pd.read_excel(xls_temp, sheet_name="Sheet1")
    except Exception as e:
        st.error(f"data(최종).xlsx 로드 실패: {e}")
        st.stop()
    
    df_temp = pd.DataFrame()
    df_temp['Province'] = df_temp_raw.iloc[:, 0].apply(clean_province_name)
    df_temp['Temp_Change'] = pd.to_numeric(df_temp_raw.iloc[:, 1], errors='coerce')
    
    # 2. 변수 데이터 로드 (variables(최종).xlsx)
    try:
        xls_vars = pd.ExcelFile("variables(최종).xlsx")
        df_vars_raw = pd.read_excel(xls_vars, sheet_name="Sheet1")
    except Exception as e:
        st.error(f"variables(최종).xlsx 로드 실패: {e}")
        st.stop()
        
    df_vars = pd.DataFrame()
    df_vars['Province'] = df_vars_raw.iloc[:, 0].apply(clean_province_name)
    
    # 2007, 2025 GDP 및 Poverty 차이 계산
    g2007 = pd.to_numeric(df_vars_raw.iloc[:, 1], errors='coerce')
    g2025 = pd.to_numeric(df_vars_raw.iloc[:, 2], errors='coerce')
    p2007 = pd.to_numeric(df_vars_raw.iloc[:, 3], errors='coerce')
    p2025 = pd.to_numeric(df_vars_raw.iloc[:, 4], errors='coerce')
    
    df_vars['GDP_diff'] = g2025 - g2007
    df_vars['Poverty_diff'] = p2025 - p2007
    
    # 표준 매칭 키 생성
    df_temp['Join_Key'] = df_temp['Province'].str.replace(r'\s+', '', regex=True).str.lower()
    df_vars['Join_Key'] = df_vars['Province'].str.replace(r'\s+', '', regex=True).str.lower()
    
    # 데이터 병합 (알파벳 정렬 순서에 상관없이 Join_Key로 매칭)
    df_final = pd.merge(df_temp, df_vars[['Join_Key', 'GDP_diff', 'Poverty_diff']], on='Join_Key', how='inner')
    
    # 결측치 및 노이즈 행 정리
    df_final = df_final[df_final['Province'].notna() & (df_final['Province'] != '')]
    df_final = df_final[~df_final['Province'].str.contains("total|average|합계|평균|province", case=False, na=False)]
    df_final = df_final.dropna(subset=['Temp_Change', 'GDP_diff', 'Poverty_diff']).reset_index(drop=True)
    
    # 정규화 연산 (0 ~ 1)
    gdp_min, gdp_max = df_final['GDP_diff'].min(), df_final['GDP_diff'].max()
    pov_min, pov_max = df_final['Poverty_diff'].min(), df_final['Poverty_diff'].max()
    
    df_final['GDP_norm'] = (df_final['GDP_diff'] - gdp_min) / (gdp_max - gdp_min + 1e-5) if gdp_max != gdp_min else 0.5
    df_final['Poverty_norm'] = (df_final['Poverty_diff'] - pov_min) / (pov_max - pov_min + 1e-5) if pov_max != pov_min else 0.5
    
    return df_final

df_final = load_and_match_data()

# GeoJSON 로드
geojson_path = "indonesia.geojson"
if not os.path.exists(geojson_path) and os.path.exists("indonesia.geojson.json"):
    geojson_path = "indonesia.geojson.json"

try:
    with open(geojson_path, "r", encoding="utf-8") as f:
        geo_data = json.load(f)
except Exception as e:
    st.error(f"지도 데이터 파일 로드 실패: {e}")
    st.stop()

# 사이드바 가중치 조절 슬라이더
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.7, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.3, 0.1)

# 실시간 시뮬레이션 계산
df_final['BCPI'] = (alpha * df_final['GDP_norm']) - (gamma * df_final['Poverty_norm'])
df_final['ETI'] = df_final['BCPI'] / (df_final['Temp_Change'].abs() + 1e-5)
df_final['순위'] = df_final['ETI'].rank(ascending=False, method='min').astype(int)

# 지도의 NAME_1과 맞출 매핑 필드 추가
df_final['Geo_Province'] = df_final['Province'].astype(str).str.strip()

# 화면 분할 출력
col1, col2 = st.columns([4, 6])

with col1:
    st.subheader("📊 시뮬레이션 결과 랭킹")
    res_df = pd.DataFrame({
        '순위': df_final['순위'],
        '주(Province)': df_final['Province'],
        'BCPI': df_final['BCPI'].round(4),
        '기온 변화량': df_final['Temp_Change'].round(4),
        '환경탄력성(ETI)': df_final['ETI'].round(4)
    })
    res_df = res_df.sort_values(by='순위').reset_index(drop=True)
    st.dataframe(res_df, use_container_width=True, height=550)

with col2:
    st.subheader("🗺️ 인도네시아 주별 환경탄력성 지도")
    m = folium.Map(location=[-2.5, 118], zoom_start=4, tiles="OpenStreetMap")
    
    threshold_scale = np.linspace(df_final['ETI'].min(), df_final['ETI'].max(), 5).tolist()

    folium.Choropleth(
        geo_data=geo_data,
        name="환경탄력성지수(ETI)",
        data=df_final,
        columns=["Geo_Province", "ETI"],
        key_on="feature.properties.NAME_1",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.4,
        threshold_scale=threshold_scale,
        legend_name="환경탄력성지수 (ETI)",
    ).add_to(m)
    
    st_folium(m, width="100%", height=550)
