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

# 대소문자, 공백, 모든 특수문자/줄바꿈을 날리고 오직 영문자만 남기는 슈퍼 매칭 함수
def make_pure_key(name):
    if pd.isna(name):
        return ""
    # 공백, 줄바꿈, 온갖 노이즈 특수문자 완벽히 제거 후 소문자 통일
    pure = re.sub(r'[^a-zA-Z]', '', str(name)).lower()
    
    # 대표적인 예외 주 이름 싱크홀 방지 보정
    if "jakarta" in pure:
        return "jakartaraya"
    if "yogyakarta" in pure:
        return "yogyakarta"
    if "aceh" in pure:
        return "aceh"
    if "bangkabelitung" in pure:
        return "kepulauanbangkabelitung"
    return pure

# 화면 표시용으로 이름을 보기 좋게 정제해 주는 맵
DISPLAY_NAMES = {
    "jakartaraya": "Jakarta Raya",
    "yogyakarta": "Yogyakarta",
    "aceh": "Aceh",
    "kepulauanbangkabelitung": "Kepulauan Bangka Belitung",
    "banten": "Banten",
    "bengkulu": "Bengkulu",
    "gorontalo": "Gorontalo",
    "jambi": "Jambi",
    "jawabarat": "Jawa Barat",
    "jawatengah": "Jawa Tengah",
    "jawatimur": "Jawa Timur",
    "kalimantanbarat": "Kalimantan Barat",
    "kalimantanselatan": "Kalimantan Selatan",
    "kalimantantengah": "Kalimantan Tengah",
    "kalimantantimur": "Kalimantan Timur",
    "kalimantanutara": "Kalimantan Utara",
    "kepulauanriau": "Kepulauan Riau",
    "lampung": "Lampung",
    "maluku": "Maluku",
    "malukuutara": "Maluku Utara",
    "nusatenggarabarat": "Nusa Tenggara Barat",
    "nusatenggaratimur": "Nusa Tenggara Timur",
    "papua": "Papua",
    "papuabarat": "Papua Barat",
    "riau": "Riau",
    "sulawesibarat": "Sulawesi Barat",
    "sulawesiselatan": "Sulawesi Selatan",
    "sulawesitengah": "Sulawesi Tengah",
    "sulawesitenggara": "Sulawesi Tenggara",
    "sulawesiutara": "Sulawesi Utara",
    "sumaterabarat": "Sumatera Barat",
    "sumateraselatan": "Sumatera Selatan",
    "sumaterautara": "Sumatera Utara",
    "bali": "Bali"
}

@st.cache_data
def load_and_match_data():
    # 1. 기온 데이터 로드
    try:
        xls_temp = pd.ExcelFile("data(최종).xlsx")
        df_temp_raw = pd.read_excel(xls_temp, sheet_name="Sheet1")
    except Exception as e:
        st.error(f"data(최종).xlsx 로드 실패: {e}")
        st.stop()
    
    df_temp = pd.DataFrame()
    df_temp['Raw_Province'] = df_temp_raw.iloc[:, 0].astype(str)
    df_temp['Temp_Change'] = pd.to_numeric(df_temp_raw.iloc[:, 1], errors='coerce')
    df_temp['Join_Key'] = df_temp['Raw_Province'].apply(make_pure_key)
    
    # 2. 변수 데이터 로드
    try:
        xls_vars = pd.ExcelFile("variables(최종).xlsx")
        df_vars_raw = pd.read_excel(xls_vars, sheet_name="Sheet1")
    except Exception as e:
        st.error(f"variables(최종).xlsx 로드 실패: {e}")
        st.stop()
        
    df_vars = pd.DataFrame()
    df_vars['Raw_Province'] = df_vars_raw.iloc[:, 0].astype(str)
    df_vars['Join_Key'] = df_vars['Raw_Province'].apply(make_pure_key)
    
    g2007 = pd.to_numeric(df_vars_raw.iloc[:, 1], errors='coerce')
    g2025 = pd.to_numeric(df_vars_raw.iloc[:, 2], errors='coerce')
    p2007 = pd.to_numeric(df_vars_raw.iloc[:, 3], errors='coerce')
    p2025 = pd.to_numeric(df_vars_raw.iloc[:, 4], errors='coerce')
    
    df_vars['GDP_diff'] = g2025 - g2007
    df_vars['Poverty_diff'] = p2025 - p2007
    
    # 3. 엑셀의 순서가 알파벳순이 아니거나 뒤섞여도 정상적으로 합칠 수 있도록 Join_Key 기준으로 완벽 병합(Merge)
    df_final = pd.merge(df_temp, df_vars[['Join_Key', 'GDP_diff', 'Poverty_diff']], on='Join_Key', how='inner')
    
    # 노이즈 행 및 합계 데이터 완전 제거
    df_final = df_final[df_final['Join_Key'] != ""]
    df_final = df_final[~df_final['Join_Key'].str.contains("total|average|sum|mean|합계|평균", na=False)]
    df_final = df_final.dropna(subset=['Temp_Change', 'GDP_diff', 'Poverty_diff']).reset_index(drop=True)
    
    # 깨진 한글/영문 이름을 표준 영문 표기로 통일
    df_final['Province'] = df_final['Join_Key'].map(DISPLAY_NAMES).fillna(df_final['Raw_Province'])
    
    # 정규화 연산 (0 ~ 1)
    gdp_min, gdp_max = df_final['GDP_diff'].min(), df_final['GDP_diff'].max()
    pov_min, pov_max = df_final['Poverty_diff'].min(), df_final['Poverty_diff'].max()
    
    df_final['GDP_norm'] = (df_final['GDP_diff'] - gdp_min) / (gdp_max - gdp_min + 1e-5) if gdp_max != gdp_min else 0.5
    df_final['Poverty_norm'] = (df_final['Poverty_diff'] - pov_min) / (pov_max - pov_min + 1e-5) if pov_max != pov_min else 0.5
    
    return df_final

df_final = load_and_match_data()

# GeoJSON 로드 및 가공
geojson_path = "indonesia.geojson"
if not os.path.exists(geojson_path) and os.path.exists("indonesia.geojson.json"):
    geojson_path = "indonesia.geojson.json"

try:
    with open(geojson_path, "r", encoding="utf-8") as f:
        geo_data = json.load(f)
except Exception as e:
    st.error(f"지도 데이터 파일 로드 실패: {e}")
    st.stop()

# GeoJSON에서 주 이름이 담긴 속성 자동 탐색 (가장 정확한 NAME_1 혹은 name 등을 매칭)
possible_keys = ['NAME_1', 'name', 'province', 'state', 'PROVINCE', 'NAME']
found_key = None
for feature in geo_data['features']:
    props = feature['properties']
    for pk in possible_keys:
        if pk in props and props[pk]:
            found_key = pk
            break
    if found_key:
        break

if not found_key and len(geo_data['features']) > 0:
    found_key = list(geo_data['features'][0]['properties'].keys())[0]

# GeoJSON의 각 구역에 비교 분석용 "Match_Key" 주입
geojson_keys = []
for feature in geo_data['features']:
    orig_name = feature['properties'].get(found_key, '')
    pure_k = make_pure_key(orig_name)
    feature['properties']['Match_Key'] = pure_k
    geojson_keys.append(pure_k)

# 데이터프레임과 지도 파일의 정렬 순서를 일치시키기 위해 동일한 매치 키 컬럼 생성
df_final['Match_Key'] = df_final['Join_Key']

# 사이드바 가중치 조절 슬라이더
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.4, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.6, 0.1)

# 실시간 시뮬레이션 계산
df_final['BCPI'] = (alpha * df_final['GDP_norm']) - (gamma * df_final['Poverty_norm'])
df_final['ETI'] = df_final['BCPI'] / (df_final['Temp_Change'].abs() + 1e-5)
df_final['순위'] = df_final['ETI'].rank(ascending=False, method='min').astype(int)

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
        columns=["Match_Key", "ETI"],
        key_on="feature.properties.Match_Key",  # 꼬여있는 정렬 순서에 대응하는 유니크 매칭 키
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.4,
        threshold_scale=threshold_scale,
        legend_name="환경탄력성지수 (ETI)",
    ).add_to(m)
    
    st_folium(m, width="100%", height=550)

# 🔍 문제 원인 해결을 위한 하단 디버그 검사기 (어떤 주가 매칭이 안 되고 있나?)
with st.expander("🔍 [문제 검사기] 엑셀 데이터 vs 지도 파일 매칭 현황 확인"):
    excel_keys = set(df_final['Match_Key'].tolist())
    map_keys = set(geojson_keys)
    
    matched = excel_keys.intersection(map_keys)
    unmatched_excel = excel_keys - map_keys
    unmatched_map = map_keys - excel_keys
    
    st.write(f"✅ **정상 매칭 성공한 주 개수:** {len(matched)}개")
    
    col_db1, col_db2 = st.columns(2)
    with col_db1:
        st.write("❌ **엑셀에는 있지만 지도파일에 없는 스펠링:**")
        if unmatched_excel:
            for k in unmatched_excel:
                original_row = df_final[df_final['Match_Key'] == k]['Raw_Province'].values[0]
                st.write(f"- `{original_row}` (인식키: `{k}`)")
        else:
            st.write("없음! 모두 완벽 매칭되었습니다.")
            
    with col_db2:
        st.write("❌ **지도파일에는 있지만 엑셀에 매칭 안 된 스펠링:**")
        if unmatched_map:
            for k in unmatched_map:
                # GeoJSON 원래 이름 찾기
                for feature in geo_data['features']:
                    if feature['properties']['Match_Key'] == k:
                        st.write(f"- `{feature['properties'].get(found_key)}` (인식키: `{k}`)")
                        break
        else:
            st.write("없음! 모든 지도 영역이 정상 매칭되었습니다.")
