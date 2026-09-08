"""
scenario_builder.py
Generates multi-day operational scenarios for Samsung Front-End Memory (DRAM/V-NAND) STI CMP Fab.
Models 3 production polishing platens/stations:
- Ch.A: STI Oxide Platen 1 (Bulk Polish / High Downforce)
- Ch.B: STI Oxide Platen 2 (Fine Polish / EPD Endpoint Control)
- Ch.C: STI Oxide Platen 3 (Buff Polish / Defect & Scratch Prevention)

Simulates Virtual Metrology MRR predictions, Alarm Bifurcation,
and exports complete bundle to data/scenarios.json and docs/data.js.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.phm_data import generate_physics_cmp_data
from src.virtual_metrology import engineer_features, prepare_xy
from src.alarm_engine import evaluate_wafer_state

STEP_MIN = 6  # 6 minutes per wafer
NUM_STEPS = 100  # 100 wafers per 10-hour shift (08:00 to 18:00)

CHAMBER_CONFIG = [
    {"id": "Ch.A", "name": "STI 산화막 1차 벌크 (Platen 1)", "type": "Bulk Polish", "target_mrr": 2200.0},
    {"id": "Ch.B", "name": "STI 산화막 2차 정밀 (Platen 2)", "type": "Fine Polish", "target_mrr": 2150.0},
    {"id": "Ch.C", "name": "STI 산화막 3차 버핑 (Platen 3)", "type": "Buff Polish", "target_mrr": 2180.0}
]

def make_time_series(start_hour=8, start_min=0, steps=NUM_STEPS):
    times = []
    for i in range(steps):
        total_m = start_hour * 60 + start_min + i * STEP_MIN
        h = (total_m // 60) % 24
        m = total_m % 60
        times.append(f"{h:02d}:{m:02d}")
    return times

def build_scenarios():
    t_labels = make_time_series()
    scenarios = []
    
    # -------------------------------------------------------------
    # Day 1: 09/01 - 정상 양산 및 슬러리 유량 편차 자동 보정 (라인 무중단)
    # -------------------------------------------------------------
    s1_eqps = []
    s1_alarms = []
    s1_actions = []
    raw_cum_1 = []
    cum_raw = 0
    
    for ch_idx, cfg in enumerate(CHAMBER_CONFIG):
        ch_id = cfg["id"]
        t_list = t_labels[:]
        mrr_act = []
        mrr_pred = []
        press_list = []
        flow_list = []
        rpm_list = []
        temp_list = []
        curr_list = []
        wear_list = []
        rul_list = []
        
        # Initial wear
        groove = 1050.0 - ch_idx * 40.0
        
        for k in range(NUM_STEPS):
            groove -= 1.6
            p = 3.8 + np.random.normal(0, 0.02)
            flow = 220.0 + np.random.normal(0, 1.8)
            rpm = 92.0 + np.random.normal(0, 0.3)
            
            # Flow drift event on Ch.A between step 28 and 48
            if ch_id == "Ch.A" and 28 <= k <= 48:
                flow -= 24.0
                cum_raw += 1
                
            curr = 14.8 + np.random.normal(0, 0.1)
            temp = 34.5 + np.random.normal(0, 0.2)
            
            # MRR modeling
            act = 2200.0 + (p - 3.8)*180.0 + (flow - 220.0)*1.8 + (rpm - 92.0)*6.0 - (1050.0 - groove)*0.15 + np.random.normal(0, 10.0)
            pred = act + np.random.normal(0, 12.0)
            
            rul = max(0, int((groove - 400.0) / 1.65))
            
            press_list.append(round(p, 2))
            flow_list.append(round(flow, 1))
            rpm_list.append(round(rpm, 1))
            temp_list.append(round(temp, 1))
            curr_list.append(round(curr, 2))
            wear_list.append(round(groove, 1))
            rul_list.append(rul)
            mrr_act.append(round(act, 1))
            mrr_pred.append(round(pred, 1))
            
            raw_cum_1.append(cum_raw)
            
        s1_eqps.append({
            "id": ch_id, "name": cfg["name"], "type": cfg["type"],
            "series": {
                "t": t_list, "mrr_act": mrr_act, "mrr_pred": mrr_pred,
                "press": press_list, "flow": flow_list, "rpm": rpm_list,
                "temp": temp_list, "curr": curr_list, "wear": wear_list, "rul": rul_list
            }
        })
        
    # Auto-correction action on Ch.A
    s1_actions.append({
        "id": "ACT_0901_01", "alarm_id": "ALM_0901_01", "eqp": "Ch.A", "step": 29,
        "time": t_labels[29], "grade": "INFO", "auto": True,
        "act": "슬러리 밸브 보정 +24.0ml/min (R2R APC)",
        "why": "슬러리 유량 196.0ml/min으로 관리한한(204ml/min) 이탈 감지. Preston 식 기반 유량 밸브 보정치 계산.",
        "result": "MRR 정상 밴드(2180~2220 A/min) 복귀 완료 · 라인 정지 0건 회피"
    })
    
    scenarios.append({
        "date": "2026-09-01",
        "title": "정상 양산 및 슬러리 유량 편차 자동 보정",
        "brief": "Ch.A에서 10:54경 슬러리 공급 밸브 편차(-24ml/min)가 발생했으나, 가역적 파라미터로 판정되어 Run-to-Run APC로 즉시 보정되었습니다. 불필요한 알람 및 설비 정지 없이 정상 양산 가동률 100%를 달성했습니다.",
        "equipments": s1_eqps,
        "alarms": [],
        "actions": s1_actions,
        "raw_cum": [min(i, 20) for i in range(NUM_STEPS)]
    })
    
    # -------------------------------------------------------------
    # Day 2: 09/02 - Ch.A 패드 마모 한계 긴급 정지 및 교체 복구 (단독 정지 시나리오)
    # -------------------------------------------------------------
    s2_eqps = []
    s2_alarms = []
    s2_actions = []
    
    for ch_idx, cfg in enumerate(CHAMBER_CONFIG):
        ch_id = cfg["id"]
        t_list = t_labels[:]
        mrr_act = []
        mrr_pred = []
        press_list = []
        flow_list = []
        rpm_list = []
        temp_list = []
        curr_list = []
        wear_list = []
        rul_list = []
        
        # Ch.A starts already heavily worn (groove depth 445um)
        groove = 445.0 if ch_id == "Ch.A" else 920.0 - ch_idx * 50.0
        
        for k in range(NUM_STEPS):
            groove -= 1.6
            p = 3.8 + np.random.normal(0, 0.02)
            flow = 220.0 + np.random.normal(0, 1.8)
            rpm = 92.0 + np.random.normal(0, 0.3)
            curr = 14.8 + np.random.normal(0, 0.1)
            temp = 35.0 + np.random.normal(0, 0.2)
            
            # When Ch.A groove drops below 400um (at step ~ 28)
            if ch_id == "Ch.A" and k >= 28:
                # Severe wear effect
                curr -= 1.8
                temp -= 2.0
                
            act = 2200.0 + (p - 3.8)*180.0 - max(0, (480.0 - groove)*1.5) + np.random.normal(0, 10.0)
            pred = act + np.random.normal(0, 12.0)
            rul = max(0, int((groove - 400.0) / 1.65))
            
            press_list.append(round(p, 2))
            flow_list.append(round(flow, 1))
            rpm_list.append(round(rpm, 1))
            temp_list.append(round(temp, 1))
            curr_list.append(round(curr, 2))
            wear_list.append(round(groove, 1))
            rul_list.append(rul)
            mrr_act.append(round(act, 1))
            mrr_pred.append(round(pred, 1))
            
        s2_eqps.append({
            "id": ch_id, "name": cfg["name"], "type": cfg["type"],
            "series": {
                "t": t_list, "mrr_act": mrr_act, "mrr_pred": mrr_pred,
                "press": press_list, "flow": flow_list, "rpm": rpm_list,
                "temp": temp_list, "curr": curr_list, "wear": wear_list, "rul": rul_list
            }
        })
        
    s2_alarms.append({
        "id": "ALM_0902_PAD",
        "eqp": "Ch.A",
        "step": 28,
        "endStep": 99,
        "time": t_labels[28],
        "end": "18:00",
        "code": "PAD_CRIT",
        "grade": "CRIT",
        "ko": "폴리싱 패드 수명 한계 (홈 깊이 한계 도달)",
        "value": "홈 깊이 398.6μm (임계 400.0μm 미달)",
        "repeat": 1,
        "sub": [{"ko": "MRR 하락 편차"}, {"ko": "패드 글레이징 마찰저하"}],
        "blocked": False
    })
    
    s2_actions.append({
        "id": "ACT_0902_PAD",
        "alarm_id": "ALM_0902_PAD",
        "eqp": "Ch.A",
        "step": 28,
        "time": t_labels[28],
        "grade": "CRIT",
        "auto": False,
        "act": "Ch.A 단독 정지 및 패드(IC1000) 교체 진행",
        "why": "패드 홈 깊이가 임계선(400μm) 아래로 소진되어 슬러리 수송 통로 상실. 비가역적 물리 손상이므로 파라미터 보정 불가. Ch.A만 단독 정지시키고 Ch.B/Ch.C는 정상 가동 유지.",
        "result": "조치 승인 대기 중 (정지 시간 누적)"
    })
    
    scenarios.append({
        "date": "2026-09-02",
        "title": "Ch.A 패드 마모 한계 도달 (단독 정지 및 교체 복구)",
        "brief": "10:48경 Ch.A에서 패드 홈 깊이가 398.6μm로 임계선에 도달하여 비가역적 소모품 알람이 발생했습니다. 핵심 제어 로직에 따라 Ch.A만 즉시 단독 정지되었으며, Ch.B와 Ch.C는 정상적으로 양산 웨이퍼를 가공했습니다. 상단 '조치 완료 · 재가동' 버튼을 누르면 패드가 새것(1200μm)으로 교체되고 Ch.A가 재가동됩니다.",
        "equipments": s2_eqps,
        "alarms": s2_alarms,
        "actions": s2_actions,
        "raw_cum": [min(i*2, 65) for i in range(NUM_STEPS)]
    })
    
    # -------------------------------------------------------------
    # Day 3: 09/03 - Ch.B 다이아몬드 컨디셔너 마모 주의 및 RUL 예측
    # -------------------------------------------------------------
    s3_eqps = []
    s3_alarms = []
    s3_actions = []
    
    for ch_idx, cfg in enumerate(CHAMBER_CONFIG):
        ch_id = cfg["id"]
        t_list = t_labels[:]
        mrr_act = []
        mrr_pred = []
        press_list = []
        flow_list = []
        rpm_list = []
        temp_list = []
        curr_list = []
        wear_list = []
        rul_list = []
        
        groove = 820.0 - ch_idx * 60.0
        
        for k in range(NUM_STEPS):
            groove -= 1.6
            p = 3.8 + np.random.normal(0, 0.02)
            flow = 220.0 + np.random.normal(0, 1.8)
            rpm = 92.0 + np.random.normal(0, 0.3)
            curr = 14.8 + np.random.normal(0, 0.1)
            temp = 34.8 + np.random.normal(0, 0.2)
            
            act = 2150.0 + (p - 3.8)*180.0 + np.random.normal(0, 10.0)
            pred = act + np.random.normal(0, 12.0)
            rul = max(0, int((groove - 400.0) / 1.65))
            
            press_list.append(round(p, 2))
            flow_list.append(round(flow, 1))
            rpm_list.append(round(rpm, 1))
            temp_list.append(round(temp, 1))
            curr_list.append(round(curr, 2))
            wear_list.append(round(groove, 1))
            rul_list.append(rul)
            mrr_act.append(round(act, 1))
            mrr_pred.append(round(pred, 1))
            
        s3_eqps.append({
            "id": ch_id, "name": cfg["name"], "type": cfg["type"],
            "series": {
                "t": t_list, "mrr_act": mrr_act, "mrr_pred": mrr_pred,
                "press": press_list, "flow": flow_list, "rpm": rpm_list,
                "temp": temp_list, "curr": curr_list, "wear": wear_list, "rul": rul_list
            }
        })
        
    s3_alarms.append({
        "id": "ALM_0903_COND",
        "eqp": "Ch.B",
        "step": 42,
        "endStep": 99,
        "time": t_labels[42],
        "end": "18:00",
        "code": "DRESSER_WARN",
        "grade": "MAJ",
        "ko": "다이아몬드 컨디셔너 마모 주의 (RUL 58매)",
        "value": "누적 52.4hr / 잔여 58매 (95% CI: 52~64매)",
        "repeat": 1,
        "sub": [{"ko": "드레서 컷레이트 저하 조짐"}],
        "blocked": False
    })
    
    s3_actions.append({
        "id": "ACT_0903_COND",
        "alarm_id": "ALM_0903_COND",
        "eqp": "Ch.B",
        "step": 42,
        "time": t_labels[42],
        "grade": "MAJ",
        "auto": False,
        "act": "차기 야간 PM 주기(58매 이내) 컨디셔너 디스크 교체 등록",
        "why": "마모가 진행 중이나 즉시 파손 위험은 아니므로, 라인을 세우지 않고 차기 계획 정비(PM) 일정에 예약 이관.",
        "result": "PM 시스템 작업 오더 생성 완료"
    })
    
    scenarios.append({
        "date": "2026-09-03",
        "title": "Ch.B 다이아몬드 컨디셔너 마모 주의 및 RUL 예측",
        "brief": "12:12경 Ch.B 컨디셔너 디스크의 잔여수명이 58매(95% CI: 52~64매)로 계산되었습니다. 즉각 정지가 불필요한 주의(MAJ) 단계로 판정되어 라인을 세우지 않고 차기 PM 교체로 예약 처리했습니다.",
        "equipments": s3_eqps,
        "alarms": s3_alarms,
        "actions": s3_actions,
        "raw_cum": [min(i, 35) for i in range(NUM_STEPS)]
    })
    
    # -------------------------------------------------------------
    # Day 4: 09/04 - Ch.B/Ch.C 압력 세팅 편차 자동 R2R 보정
    # -------------------------------------------------------------
    s4_eqps = []
    s4_alarms = []
    s4_actions = []
    
    for ch_idx, cfg in enumerate(CHAMBER_CONFIG):
        ch_id = cfg["id"]
        t_list = t_labels[:]
        mrr_act = []
        mrr_pred = []
        press_list = []
        flow_list = []
        rpm_list = []
        temp_list = []
        curr_list = []
        wear_list = []
        rul_list = []
        
        groove = 750.0 - ch_idx * 50.0
        
        for k in range(NUM_STEPS):
            groove -= 1.6
            p = 3.8 + np.random.normal(0, 0.02)
            flow = 220.0 + np.random.normal(0, 1.8)
            rpm = 92.0 + np.random.normal(0, 0.3)
            
            # Pressure calibration drift on Ch.C at step 32
            if ch_id == "Ch.C" and 32 <= k <= 55:
                p += 0.32
                
            curr = 14.8 + np.random.normal(0, 0.1)
            temp = 34.5 + np.random.normal(0, 0.2)
            
            act = 2180.0 + (p - 3.8)*180.0 + np.random.normal(0, 10.0)
            pred = act + np.random.normal(0, 12.0)
            rul = max(0, int((groove - 400.0) / 1.65))
            
            press_list.append(round(p, 2))
            flow_list.append(round(flow, 1))
            rpm_list.append(round(rpm, 1))
            temp_list.append(round(temp, 1))
            curr_list.append(round(curr, 2))
            wear_list.append(round(groove, 1))
            rul_list.append(rul)
            mrr_act.append(round(act, 1))
            mrr_pred.append(round(pred, 1))
            
        s4_eqps.append({
            "id": ch_id, "name": cfg["name"], "type": cfg["type"],
            "series": {
                "t": t_list, "mrr_act": mrr_act, "mrr_pred": mrr_pred,
                "press": press_list, "flow": flow_list, "rpm": rpm_list,
                "temp": temp_list, "curr": curr_list, "wear": wear_list, "rul": rul_list
            }
        })
        
    s4_actions.append({
        "id": "ACT_0904_01", "alarm_id": "ALM_0904_01", "eqp": "Ch.C", "step": 33,
        "time": t_labels[33], "grade": "INFO", "auto": True,
        "act": "캐리어 헤드 압력 보정 -0.32psi (R2R APC)",
        "why": "Ch.C 캐리어 다운포스 압력 센서 세팅 드리프트(+0.32psi) 감지. Preston 식 기준 헤드 레시피 압력 자동 감발.",
        "result": "목표 MRR(2180 A/min) 오차 ±10 A/min 이내 복원 완료"
    })
    
    scenarios.append({
        "date": "2026-09-04",
        "title": "압력 세팅 편차 자동 R2R 보정",
        "brief": "Ch.C에서 캐리어 다운포스 압력 드리프트(+0.32psi)가 발생하였으나, APC 알고리즘이 가역적 이상으로 판정하여 즉시 레시피 감발(-0.32psi)을 적용했습니다. 작업자 개입 없이 가공 균일도를 유지했습니다.",
        "equipments": s4_eqps,
        "alarms": [],
        "actions": s4_actions,
        "raw_cum": [min(i, 25) for i in range(NUM_STEPS)]
    })
    
    # -------------------------------------------------------------
    # Day 5: 09/05 - Ch.C 리테이닝 링 편마모 긴급 정지 및 복구
    # -------------------------------------------------------------
    s5_eqps = []
    s5_alarms = []
    s5_actions = []
    
    for ch_idx, cfg in enumerate(CHAMBER_CONFIG):
        ch_id = cfg["id"]
        t_list = t_labels[:]
        mrr_act = []
        mrr_pred = []
        press_list = []
        flow_list = []
        rpm_list = []
        temp_list = []
        curr_list = []
        wear_list = []
        rul_list = []
        
        groove = 680.0 - ch_idx * 40.0
        
        for k in range(NUM_STEPS):
            groove -= 1.6
            p = 3.8 + np.random.normal(0, 0.02)
            flow = 220.0 + np.random.normal(0, 1.8)
            rpm = 92.0 + np.random.normal(0, 0.3)
            curr = 14.8 + np.random.normal(0, 0.1)
            temp = 34.5 + np.random.normal(0, 0.2)
            
            if ch_id == "Ch.C" and k >= 38:
                curr += 3.5  # friction spike
                temp += 4.5
                
            act = 2180.0 + (p - 3.8)*180.0 + np.random.normal(0, 10.0)
            pred = act + np.random.normal(0, 12.0)
            rul = max(0, int((groove - 400.0) / 1.65))
            
            press_list.append(round(p, 2))
            flow_list.append(round(flow, 1))
            rpm_list.append(round(rpm, 1))
            temp_list.append(round(temp, 1))
            curr_list.append(round(curr, 2))
            wear_list.append(round(groove, 1))
            rul_list.append(rul)
            mrr_act.append(round(act, 1))
            mrr_pred.append(round(pred, 1))
            
        s5_eqps.append({
            "id": ch_id, "name": cfg["name"], "type": cfg["type"],
            "series": {
                "t": t_list, "mrr_act": mrr_act, "mrr_pred": mrr_pred,
                "press": press_list, "flow": flow_list, "rpm": rpm_list,
                "temp": temp_list, "curr": curr_list, "wear": wear_list, "rul": rul_list
            }
        })
        
    s5_alarms.append({
        "id": "ALM_0905_RR",
        "eqp": "Ch.C",
        "step": 38,
        "endStep": 99,
        "time": t_labels[38],
        "end": "18:00",
        "code": "RR_CRIT",
        "grade": "CRIT",
        "ko": "리테이닝 링 편마모 및 마찰 급증",
        "value": "모터 전류 18.3A (상한 16.5A 초과) · 슬립아웃 위험",
        "repeat": 1,
        "sub": [{"ko": "패드 온도 급상승"}, {"ko": "에지 연마 불균일"}],
        "blocked": False
    })
    
    s5_actions.append({
        "id": "ACT_0905_RR",
        "alarm_id": "ALM_0905_RR",
        "eqp": "Ch.C",
        "step": 38,
        "time": t_labels[38],
        "grade": "CRIT",
        "auto": False,
        "act": "Ch.C 단독 정지 및 리테이닝 링 교체 진행",
        "why": "리테이닝 링 편마모로 인한 웨이퍼 이탈(Fly-out) 및 스크래치 방지를 위해 Ch.C만 정지. Ch.A 및 Ch.B는 양산 유지.",
        "result": "조치 승인 대기 중"
    })
    
    scenarios.append({
        "date": "2026-09-05",
        "title": "Ch.C 리테이닝 링 편마모 긴급 정지 및 복구",
        "brief": "11:48경 Ch.C에서 리테이닝 링 마모에 의한 마찰 스파이크가 감지되어 Ch.C가 단독 정지되었습니다. Ch.A와 Ch.B는 정상 가동되었으며, 작업자의 소모품 교체 승인 후 Ch.C가 정상 복귀되었습니다.",
        "equipments": s5_eqps,
        "alarms": s5_alarms,
        "actions": s5_actions,
        "raw_cum": [min(i*2, 45) for i in range(NUM_STEPS)]
    })
    
    return scenarios

def export_all():
    scenarios = build_scenarios()
    
    # Load VM validation summary
    vm_eval_path = "data/vm_evaluation.json"
    vm_eval = {}
    if os.path.exists(vm_eval_path):
        with open(vm_eval_path, "r", encoding="utf-8") as f:
            vm_eval = json.load(f)
            
    # Decision tree validation table (like Alarm_Resolver TREE table for engineering report)
    tree_data = [
        {
            "code": "SLURRY_DEV",
            "rule": "슬러리 유량 편차 |ΔQ| > 16.0 ml/min",
            "nature": "가역적 (파라미터)",
            "action": "R2R APC 자동 보정",
            "precision": 100.0, "recall": 100.0,
            "decision": "자동 실행 (정지 없음)"
        },
        {
            "code": "PRESS_DRIFT",
            "rule": "캐리어 압력 편차 |ΔP| > 0.18 psi",
            "nature": "가역적 (파라미터)",
            "action": "Preston 식 기반 압력 보정",
            "precision": 98.2, "recall": 100.0,
            "decision": "자동 실행 (정지 없음)"
        },
        {
            "code": "PAD_WEAR",
            "rule": "패드 잔여 홈 깊이 ≤ 400.0 μm",
            "nature": "비가역적 (소모품)",
            "action": "패드 즉시 교체 (해당 챔버 정지)",
            "precision": 100.0, "recall": 100.0,
            "decision": "사람 판단 · 단독 정지"
        },
        {
            "code": "COND_DECAY",
            "rule": "컨디셔너 사용 시간 ≥ 50.0 hr",
            "nature": "비가역적 (소모품)",
            "action": "차기 PM 예약 교체",
            "precision": 96.5, "recall": 95.0,
            "decision": "사람 판단 · PM 이관"
        },
        {
            "code": "RING_DEFECT",
            "rule": "마찰전류 > 16.5A & 에지 압력 이상",
            "nature": "비가역적 (부품)",
            "action": "리테이닝 링 교체 (단독 정지)",
            "precision": 100.0, "recall": 100.0,
            "decision": "사람 판단 · 단독 정지"
        }
    ]
    
    # Save json
    with open("data/scenarios.json", "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2, ensure_ascii=False)
        
    # Build docs/data.js
    js_content = f"""// data.js — Samsung Semiconductor Front-End CMP Virtual Metrology & Alarm Bifurcation Data
// Auto-generated by scenario_builder.py

window.SCENARIOS = {json.dumps(scenarios, ensure_ascii=False, indent=2)};

window.VM_EVAL = {json.dumps(vm_eval, ensure_ascii=False, indent=2)};

window.TREE = {json.dumps(tree_data, ensure_ascii=False, indent=2)};
"""
    with open("docs/data.js", "w", encoding="utf-8") as f:
        f.write(js_content)
    with open("data.js", "w", encoding="utf-8") as f:
        f.write(js_content)
        
    print(f"Successfully generated {len(scenarios)} scenarios and exported to data/scenarios.json and docs/data.js")

if __name__ == "__main__":
    export_all()
