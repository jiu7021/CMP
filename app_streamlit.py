"""
app_streamlit.py
Streamlit Dashboard for Semiconductor CMP Virtual Metrology & Alarm Bifurcation.
Run locally: streamlit run app_streamlit.py
"""

import os
import json
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(
    page_title="CMP Virtual Metrology & Alarm Bifurcation Simulator",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load scenarios
data_path = "data/scenarios.json"
if not os.path.exists(data_path):
    from src.scenario_builder import export_all
    export_all()

with open(data_path, "r", encoding="utf-8") as f:
    scenarios = json.load(f)

# Sidebar
st.sidebar.title("⚙️ CMP 가상계측 & 알람 이원화")
st.sidebar.caption("삼성전자 메모리 전공정(STI/W/Cu) 3-Chamber Fab 시뮬레이터")

day_options = [f"{d['date']} : {d['title']}" for d in scenarios]
selected_day_str = st.sidebar.selectbox("📅 시나리오 일자 선택", day_options, index=1)
selected_day_idx = day_options.index(selected_day_str)
cur_day = scenarios[selected_day_idx]

st.sidebar.divider()
st.sidebar.markdown("### 🎛️ 시뮬레이션 컨트롤")
step_val = st.sidebar.slider("웨이퍼 가공 시점 (시간 진행)", 0, 99, 50, help="08:00부터 18:00까지 웨이퍼 가공 스텝")

# Session state for manual recovery
if "halted_chambers" not in st.session_state:
    st.session_state.halted_chambers = {}

cur_date = cur_day["date"]
if cur_date not in st.session_state.halted_chambers:
    st.session_state.halted_chambers[cur_date] = set()

# Main Title
st.title("반도체 CMP 가상계측 & 알람 이원화 시뮬레이터")
st.caption(f"**{cur_day['date']}** — {cur_day['title']}")

st.info(f"💡 **AI 양산 브리핑**: {cur_day['brief']}")

# Detect if any chamber triggered CRIT alarm up to current step
crit_alarms = [a for a in cur_day["alarms"] if a["step"] <= step_val and a["grade"] == "CRIT"]
for a in crit_alarms:
    ch = a["eqp"]
    # If not already cleared by user
    if ch not in st.session_state.halted_chambers[cur_date]:
        st.session_state.halted_chambers[cur_date].add(ch)

# Check active halted chambers
halted_list = list(st.session_state.halted_chambers[cur_date])

# Alert banner if halted
if halted_list:
    st.error(f"""
    🚨 **[단독 정지 경보]**: {', '.join(halted_list)} 챔버의 소모품(패드) 마모 한계로 **해당 챔버가 단독 정지**되었습니다!
    - 타 챔버는 정상 가동 중이며, 조업 시간은 계속 흐릅니다.
    - 패드 교체(PM) 승인 전까지 정지 손실이 누적됩니다.
    """)
    if st.button("🔧 소모품(패드) 교체 완료 · 챔버 재가동 승인"):
        st.session_state.halted_chambers[cur_date].clear()
        st.success("소모품 교체가 완료되어 챔버가 정상 양산으로 복귀했습니다!")
        st.rerun()

# KPI Metric Row
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
raw_alarm_count = cur_day["raw_cum"][step_val]
actions_so_far = [c for c in cur_day["actions"] if c["step"] <= step_val]
auto_actions = [c for c in actions_so_far if c["auto"]]
human_alarms = [a for a in cur_day["alarms"] if a["step"] <= step_val]
halt_minutes = (len(halted_list) * (step_val - 28) * 6) if halted_list and step_val > 28 else 0

kpi1.metric("단순 센서 임계 초과", f"{raw_alarm_count} 건")
kpi2.metric("R2R 자동 보정 완료", f"{len(auto_actions)} 건", "무중단 복구")
kpi3.metric("사람 판단 필요 알람", f"{len(human_alarms)} 건", "소모품 PM")
kpi4.metric("회피한 라인 정지", f"{len(auto_actions)} 회", "APC 효과")
kpi5.metric("정지 손실 시간", f"{max(0, halt_minutes)} 분", "단독 정지" if halted_list else "정상")

st.divider()

# Chamber Tab Views
st.subheader("📊 챔버별 실시간 센서 및 가상계측 트렌드")
ch_names = [e["id"] + " : " + e["name"] for e in cur_day["equipments"]]
selected_ch_tab = st.radio("공정 챔버 선택", ch_names, horizontal=True)
selected_ch_id = selected_ch_tab.split(" : ")[0]

eqp_data = next(e for e in cur_day["equipments"] if e["id"] == selected_ch_id)
series = eqp_data["series"]
t_slice = series["t"][:step_val + 1]

# Display status badge
is_ch_halted = selected_ch_id in st.session_state.halted_chambers[cur_date]
if is_ch_halted:
    st.warning(f"⚠️ **{selected_ch_id} 상태: 정지 (HALTED)** — 모터 회전수 0 RPM, 압력 소멸, 양산 웨이퍼 미가공 상태")
else:
    st.success(f"🟢 **{selected_ch_id} 상태: 정상 양산 가동 중 (RUNNING)**")

# Prepare DataFrame for plotting
plot_df = pd.DataFrame({
    "시간": t_slice,
    "MRR 실측값 (Å/min)": series["mrr_act"][:step_val + 1],
    "가상계측 예측값 (Å/min)": series["mrr_pred"][:step_val + 1],
    "다운포스 압력 (psi)": series["press"][:step_val + 1],
    "슬러리 유량 (ml/min)": series["flow"][:step_val + 1],
    "마찰 전류 (A)": series["curr"][:step_val + 1],
    "패드 잔여 홈깊이 (μm)": series["wear"][:step_val + 1],
    "패드 잔여수명 (웨이퍼)": series["rul"][:step_val + 1]
}).set_index("시간")

col_a, col_b = st.columns(2)
with col_a:
    st.markdown("#### 1. 가상계측 MRR (실측 vs 예측)")
    st.line_chart(plot_df[["MRR 실측값 (Å/min)", "가상계측 예측값 (Å/min)"]])

    st.markdown("#### 2. 슬러리 공급 유량 (ml/min)")
    st.line_chart(plot_df[["슬러리 유량 (ml/min)"]])

with col_b:
    st.markdown("#### 3. 폴리싱 패드 잔여 홈 깊이 & RUL (μm)")
    st.line_chart(plot_df[["패드 잔여 홈깊이 (μm)"]])

    st.markdown("#### 4. 캐리어 다운포스 압력 (psi)")
    st.line_chart(plot_df[["다운포스 압력 (psi)"]])

st.divider()

# History Tables
col_log1, col_log2 = st.columns(2)
with col_log1:
    st.subheader("🚨 사람 개입 알람 목록 (소모품 마모)")
    if human_alarms:
        for a in human_alarms:
            st.error(f"**[{a['time']}] {a['eqp']} — {a['ko']}** ({a['grade']})\n- 측정치: {a['value']}\n- 조치: 비가역 소모품 교체 및 단독 정지")
    else:
        st.caption("현재 시점까지 발생한 사람 개입 알람이 없습니다.")

with col_log2:
    st.subheader("⚡ 자동 보정 이력 타임라인 (무중단)")
    if auto_actions:
        for act in auto_actions:
            st.success(f"**[{act['time']}] {act['eqp']} — {act['act']}**\n- 원인: {act['why']}\n- 결과: {act['result']}")
    else:
        st.caption("현재 시점까지 적용된 자동 보정 이력이 없습니다.")

st.sidebar.markdown("---")
st.sidebar.markdown("🔗 **[GitHub Pages 정적 시뮬레이터 실행하기](./docs/index.html)**")
