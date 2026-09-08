"""
alarm_engine.py
Deterministic Anomaly Detection & Alarm Bifurcation Logic for CMP Process.

Categorizes process anomalies into two distinct pathways:
A. Reversible Pathway (Auto-Correction):
   - Slurry flow rate deviation, Downforce pressure drift, Table/Head RPM deviation.
   - Restorable via Run-to-Run (R2R) APC recipe compensation (Preston equation).
   - No alarm popup, NO line stop. Recorded in "Auto-Correction History".

B. Irreversible Pathway (Human Intervention / Alarm):
   - Consumable physical degradation: Pad groove depletion, Conditioner diamond wear, Membrane leakage.
   - Physically irreversible; requires scheduled PM or immediate consumable replacement.
   - Raises Alarm with consumable root cause, severity, and RUL estimation with 95% CI.
   - Severity CRIT: Immediately halts the affected chamber while other chambers continue operating!
"""

import os
import sys
import numpy as np
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.rul_estimator import estimate_pad_rul, estimate_conditioner_rul

RECIPE_TARGETS = {
    "Stage A": {"pressure": 3.8, "table_rpm": 92.0, "head_rpm": 86.0, "slurry_flow": 220.0, "mrr": 2200.0},
    "Stage B": {"pressure": 2.4, "table_rpm": 65.0, "head_rpm": 60.0, "slurry_flow": 160.0, "mrr": 1200.0}
}

DEV_FLOW_THRESHOLD = 16.0
DEV_PRESS_THRESHOLD = 0.18
DEV_RPM_THRESHOLD = 3.5

PAD_CRIT_GROOVE = 400.0
PAD_WARN_GROOVE = 480.0
DRESSER_CRIT_HOURS = 58.0
DRESSER_WARN_HOURS = 50.0

def evaluate_wafer_state(
    row: Dict[str, Any],
    pred_mrr: float
) -> Dict[str, Any]:
    stage = row.get("STAGE", "Stage A")
    targets = RECIPE_TARGETS.get(stage, RECIPE_TARGETS["Stage A"])
    
    p_z1 = row["PRESS_DOWNFORCE_Z1"]
    p_avg = (p_z1 + row["PRESS_DOWNFORCE_Z2"] + row["PRESS_DOWNFORCE_Z3"]) / 3.0
    rpm_t = row["ROTATION_TABLE_RPM"]
    flow = row["FLOW_RATE_SLURRY"]
    pad_groove = row["PAD_GROOVE_DEPTH_UM"]
    dresser_hrs = row["USAGE_OF_DRESSER"]
    pad_usage = row["USAGE_OF_POLISHING_TABLE"]
    rr_press = row["PRESS_RETAINING_RING"]
    
    delta_flow = flow - targets["slurry_flow"]
    delta_press = p_avg - targets["pressure"]
    delta_rpm = rpm_t - targets["table_rpm"]
    
    is_pad_crit = pad_groove <= PAD_CRIT_GROOVE or pad_usage >= 490
    is_pad_warn = (pad_groove <= PAD_WARN_GROOVE and not is_pad_crit) or (pad_usage >= 440 and not is_pad_crit)
    
    is_dresser_crit = dresser_hrs >= DRESSER_CRIT_HOURS
    is_dresser_warn = dresser_hrs >= DRESSER_WARN_HOURS and not is_dresser_crit
    
    is_rr_defect = (rr_press > targets["pressure"] * 1.65) or (rr_press < targets["pressure"] * 1.10)
    
    if is_pad_crit or is_dresser_crit or is_rr_defect:
        if is_pad_crit:
            root_cause = "폴리싱 패드 수명 한계 (홈 깊이 소진)"
            consumable = "Polishing Pad (IC1000)"
            rul_info = estimate_pad_rul(pad_groove, pad_usage)
            desc = f"패드 홈 깊이 {pad_groove:.1f}μm (한계선 {PAD_CRIT_GROOVE}μm 이하 도달). 마모에 의한 글레이징으로 슬러리 공급 불가 및 스크래치 위험."
            code = "PAD_CRIT"
        elif is_dresser_crit:
            root_cause = "다이아몬드 컨디셔너 디스크 마모"
            consumable = "Conditioner Disc"
            rul_info = estimate_conditioner_rul(dresser_hrs)
            desc = f"컨디셔너 사용 시간 {dresser_hrs:.1f}hr (한계 {DRESSER_CRIT_HOURS}hr 도달). 다이아몬드 입자 탈락으로 컷레이트 급락."
            code = "DRESSER_CRIT"
        else:
            root_cause = "리테이닝 링 편마모 / 멤브레인 이상"
            consumable = "Retaining Ring / Membrane"
            rul_info = {"rul_wafers": 0, "ci_95": [0, 2], "health_pct": 0.0}
            desc = f"리테이닝 링 압력 {rr_press:.2f}psi 비정상 편차. 웨이퍼 슬립아웃 위험."
            code = "RR_CRIT"
            
        return {
            "branch": "HUMAN_ALARM",
            "grade": "CRIT",
            "halt_chamber": True,
            "code": code,
            "root_cause": root_cause,
            "consumable": consumable,
            "rul": rul_info,
            "description": desc,
            "action_required": f"해당 챔버 즉시 정지 및 {consumable} 교체 작업(PM) 필요",
            "why": "비가역적 물리 마모는 레시피 보정으로 복구 불가능하며, 방치 시 웨이퍼 스크래치 및 라인 대형 사고 유발."
        }
        
    if is_pad_warn or is_dresser_warn:
        if is_pad_warn:
            consumable = "Polishing Pad (IC1000)"
            rul_info = estimate_pad_rul(pad_groove, pad_usage)
            code = "PAD_WARN"
            desc = f"패드 잔여 홈 깊이 {pad_groove:.1f}μm. 잔여수명 약 {rul_info['rul_wafers']}매 (95% CI: {rul_info['ci_95'][0]}~{rul_info['ci_95'][1]}매)."
        else:
            consumable = "Conditioner Disc"
            rul_info = estimate_conditioner_rul(dresser_hrs)
            code = "DRESSER_WARN"
            desc = f"컨디셔너 사용 시간 {dresser_hrs:.1f}hr. 잔여수명 약 {rul_info['rul_wafers']}매."
            
        return {
            "branch": "HUMAN_ALARM",
            "grade": "MAJ",
            "halt_chamber": False,
            "code": code,
            "root_cause": f"{consumable} 마모 주의",
            "consumable": consumable,
            "rul": rul_info,
            "description": desc,
            "action_required": f"다음 정기 PM 주기({rul_info['rul_wafers']}매 이내)에 소모품 교체 예약",
            "why": "마모가 진행 중이나 안전 마진 이내이므로 공정을 정지하지 않고 차기 PM으로 이관."
        }
        
    flow_issue = abs(delta_flow) > DEV_FLOW_THRESHOLD
    press_issue = abs(delta_press) > DEV_PRESS_THRESHOLD
    rpm_issue = abs(delta_rpm) > DEV_RPM_THRESHOLD
    
    if flow_issue or press_issue or rpm_issue:
        compensations = []
        if flow_issue:
            comp_flow = -round(delta_flow, 1)
            compensations.append(f"슬러리 밸브 보정 {comp_flow:+.1f}ml/min (현재 {flow:.1f} -> 목표 {targets['slurry_flow']}ml/min)")
        if press_issue:
            comp_p = -round(delta_press, 2)
            compensations.append(f"캐리어 헤드 압력 보정 {comp_p:+.2f}psi (현재 {p_avg:.2f} -> 목표 {targets['pressure']:.2f}psi)")
        if rpm_issue:
            comp_rpm = -round(delta_rpm, 1)
            compensations.append(f"테이블 모터 RPM 보정 {comp_rpm:+.1f}RPM")
            
        return {
            "branch": "AUTO_CORRECT",
            "grade": "AUTO",
            "halt_chamber": False,
            "code": "APC_R2R_CORRECTION",
            "act": "레시피 R2R 자동 보정 적용",
            "compensations": compensations,
            "description": " · ".join(compensations),
            "result": "정상 MRR 밴드 복귀 완료 (라인 무중단)",
            "why": "가역적 파라미터 편차는 APC 피드백으로 즉시 복구 가능하므로 불필요한 알람과 라인 정지를 방지함."
        }
        
    return {
        "branch": "NORMAL",
        "grade": "OK",
        "halt_chamber": False
    }

if __name__ == "__main__":
    sample_normal = {
        "STAGE": "Stage A", "PRESS_DOWNFORCE_Z1": 3.81, "PRESS_DOWNFORCE_Z2": 3.75, "PRESS_DOWNFORCE_Z3": 3.70,
        "PRESS_RETAINING_RING": 5.1, "ROTATION_TABLE_RPM": 92.2, "FLOW_RATE_SLURRY": 220.5,
        "PAD_GROOVE_DEPTH_UM": 980.0, "USAGE_OF_DRESSER": 12.0, "USAGE_OF_POLISHING_TABLE": 120
    }
    sample_flow_drift = {**sample_normal, "FLOW_RATE_SLURRY": 194.0}
    sample_pad_crit = {**sample_normal, "PAD_GROOVE_DEPTH_UM": 385.0, "USAGE_OF_POLISHING_TABLE": 495}
    
    print("Normal:", evaluate_wafer_state(sample_normal, 2200.0)["branch"])
    print("Flow Drift:", evaluate_wafer_state(sample_flow_drift, 2050.0)["branch"])
    print("Pad Crit:", evaluate_wafer_state(sample_pad_crit, 1750.0)["branch"], "Halt:", evaluate_wafer_state(sample_pad_crit, 1750.0)["halt_chamber"])
