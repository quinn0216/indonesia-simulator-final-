import streamlit as st
import pandas as pd
import numpy as np
import folium
import json
import re
from streamlit_folium import st_folium

st.set_page_config(layout="wide")
st.title("🇮🇩 인도네시아 주별 환경탄력성 지수 시뮬레이터")
st.markdown("가중치를 조절하면 우측 지도의 주별 색상과 좌측 랭킹이 실시간으로 시각화됩니다.")

def clean_province_name(name):
    if pd.isna(name):
        return ""
    name_str = str(name).replace('\n', ' ').strip()
    return re.sub(r'\s+', ' ', name_str)

def load_and_match_data():
    # 1. 기온 데이터 로드 (data(찐최종).xlsx)
    try:
        xls_temp = pd.ExcelFile("data(찐최종).xlsx")
        df_temp_raw = pd.read_excel(xls_temp, sheet_name="Sheet1")
    except Exception as e:
        st.error(f"data(찐최종).xlsx 로드 실패: {e}")
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
    df_vars['Province_Var'] = df_vars_raw.iloc[:, 0].apply(clean_province_name)
    
    g2007 = pd.to_numeric(df_vars_raw.iloc[:, 1], errors='coerce')
    g2025 = pd.to_numeric(df_vars_raw.iloc[:, 2], errors='coerce')
    p2007 = pd.to_numeric(df_vars_raw.iloc[:, 3], errors='coerce')
    p2025 = pd.to_numeric(df_vars_raw.iloc[:, 4], errors='coerce')
    
    df_vars['GDP_diff'] = g2025 - g2007
    df_vars['Poverty_diff'] = p2025 - p2007
    
    # 엑셀 파일 간 하이픈/공백 오차를 무시하고 병합하기 위한 키
    df_temp['Join_Key'] = df_temp['Province'].str.replace(r'[\s\-]+', '', regex=True).str.lower()
    df_vars['Join_Key'] = df_vars['Province_Var'].str.replace(r'[\s\-]+', '', regex=True).str.lower()
    
    # 병합
    df_final = pd.merge(df_temp, df_vars[['Join_Key', 'GDP_diff', 'Poverty_diff']], on='Join_Key', how='inner')
    
    # 불필요 행 제거 및 정제
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
geojson_path = "indonesia.json"
try:
    with open(geojson_path, "r", encoding="utf-8") as f:
        geo_data = json.load(f)
except Exception as e:
    st.error(f"지도 데이터 파일 로드 실패: {e}")
    st.stop()

# 사이드바 가중치 설정
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.7, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.3, 0.1)

# 실시간 시뮬레이션 계산
df_final['BCPI'] = (alpha * df_final['GDP_norm']) - (gamma * df_final['Poverty_norm'])
df_final['ETI'] = df_final['BCPI'] / (df_final['Temp_Change'].abs() + 1e-5)
df_final['순위'] = df_final['ETI'].rank(ascending=False, method='min').astype(int)

# 💡 [핵심 해결] GeoJSON 지도(GADM 2.8)의 NAME_1 키값과 엑셀 이름을 1:1 강제 일치
map_name_correct = {
    'Irian Jaya Barat': 'Irian Jaya Barat',
    'Papua Barat': 'Irian Jaya Barat',
    'Bangka-Belitung': 'Bangka-Belitung',
    'Bangka Belitung': 'Bangka-Belitung',
    'Kepulauan Bangka Belitung': 'Bangka-Belitung',
    'Jakarta Raya': 'Jakarta Raya',
    'Jakarta': 'Jakarta Raya'
}

df_final['Geo_Name'] = df_final['Province'].replace(map_name_correct)

# 화면 분할 출력
col1, col2 = st.columns([4, 6])

with col1:
    st.subheader("📊 시뮬레이션 결과 랭킹")
    res_df = pd.DataFrame({
        '순위': df_final['순위'],
        '주(Province)': df_final['Province'],  # 이미지 속 엑셀 이름 그대로 표출
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
        columns=["Geo_Name", "ETI"],  # 지도가 인식할 수 있도록 보정된 컬럼 전달
        key_on="feature.properties.NAME_1",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.4,
        threshold_scale=threshold_scale,
        legend_name="환경탄력성지수 (ETI)",
    ).add_to(m)
    
    st_folium(m, width="100%", height=550)
