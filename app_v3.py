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

# 양 끝 공백 및 줄바꿈을 지워주는 기본 클리닝 함수
def clean_province_name(name):
    if pd.isna(name):
        return ""
    name_str = str(name).replace('\n', ' ').strip()
    name_str = re.sub(r'\s+', ' ', name_str)
    return name_str

@st.cache_data
def load_and_match_data():
    # 1. 기온 데이터 로드
    try:
        xls_temp = pd.ExcelFile("data(찐최종).xlsx")
        df_temp_raw = pd.read_excel(xls_temp, sheet_name="Sheet1")
    except Exception as e:
        st.error(f"data(찐최종).xlsx 로드 실패: {e}")
        st.stop()
    
    df_temp = pd.DataFrame()
    df_temp['Province'] = df_temp_raw.iloc[:, 0].apply(clean_province_name)
    df_temp['Temp_Change'] = pd.to_numeric(df_temp_raw.iloc[:, 1], errors='coerce')
    
    # 2. 변수 데이터 로드
    try:
        xls_vars = pd.ExcelFile("variables(최종).xlsx")
        df_vars_raw = pd.read_excel(xls_vars, sheet_name="Sheet1")
    except Exception as e:
        st.error(f"variables(최종).xlsx 로드 실패: {e}")
        st.stop()
        
    df_vars = pd.DataFrame()
    df_vars['Province'] = df_vars_raw.iloc[:, 0].apply(clean_province_name)
    
    # GDP 및 Poverty 차이 계산
    g2007 = pd.to_numeric(df_vars_raw.iloc[:, 1], errors='coerce')
    g2025 = pd.to_numeric(df_vars_raw.iloc[:, 2], errors='coerce')
    p2007 = pd.to_numeric(df_vars_raw.iloc[:, 3], errors='coerce')
    p2025 = pd.to_numeric(df_vars_raw.iloc[:, 4], errors='coerce')
    
    df_vars['GDP_diff'] = g2025 - g2007
    df_vars['Poverty_diff'] = p2025 - p2007
    
    # 매칭용 조인 키 (공백 제거, 소문자화)
    df_temp['Join_Key'] = df_temp['Province'].str.replace(r'\s+', '', regex=True).str.lower()
    df_vars['Join_Key'] = df_vars['Province'].str.replace(r'\s+', '', regex=True).str.lower()
    
    # 데이터 병합
    df_final = pd.merge(df_temp, df_vars[['Join_Key', 'GDP_diff', 'Poverty_diff']], on='Join_Key', how='inner')
    
    # 불필요한 행 제거
    df_final = df_final[df_final['Province'].notna() & (df_final['Province'] != '')]
    df_final = df_final[~df_final['Province'].str.contains("total|average|합계|평균", case=False, na=False)]
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
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.3, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.7, 0.1)

# 실시간 시뮬레이션 계산
df_final['BCPI'] = (alpha * df_final['GDP_norm']) - (gamma * df_final['Poverty_norm'])
df_final['ETI'] = df_final['BCPI'] / (df_final['Temp_Change'].abs() + 1e-5)
df_final['순위'] = df_final['ETI'].rank(ascending=False, method='min').astype(int)

# 지도의 NAME_1과 정확하게 1:1 결합하기 위한 칼럼 매핑
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
