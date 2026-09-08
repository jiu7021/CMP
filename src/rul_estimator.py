"""
rul_estimator.py
Remaining Useful Life (RUL) Estimator for CMP Consumables:
- Polishing Pad Groove Depth Wear (IC1000 polyurethane pad)
- Diamond Conditioner Disc Cut-Rate Decay
Calculates point estimate and 95% confidence intervals.
"""

import numpy as np
from typing import Dict, Any

PAD_INITIAL_GROOVE_UM = 1200.0
PAD_CRITICAL_GROOVE_UM = 400.0
PAD_WARN_GROOVE_UM = 480.0
PAD_WEAR_RATE_PER_WAFER = 1.65  # um/wafer
PAD_WEAR_STD = 0.12

CONDITIONER_LIMIT_HOURS = 60.0
CONDITIONER_WARN_HOURS = 50.0

def estimate_pad_rul(current_groove_um: float, current_wafer_count: int) -> Dict[str, Any]:
    """
    Estimates Remaining Useful Life (RUL) in wafer count for the polishing pad.
    Returns expected RUL, 95% confidence interval, and health score (%).
    """
    remaining_depth = max(current_groove_um - PAD_CRITICAL_GROOVE_UM, 0.0)
    
    # Adaptive wear rate based on observed trajectory
    if current_wafer_count > 20:
        observed_rate = (PAD_INITIAL_GROOVE_UM - current_groove_um) / max(current_wafer_count, 1)
        wear_rate = 0.7 * observed_rate + 0.3 * PAD_WEAR_RATE_PER_WAFER
    else:
        wear_rate = PAD_WEAR_RATE_PER_WAFER
        
    wear_rate = max(wear_rate, 0.5)
    rul_wafers = remaining_depth / wear_rate
    
    # 95% Confidence Interval based on stochastic wear variance
    sigma_rul = (remaining_depth / (wear_rate ** 2)) * PAD_WEAR_STD
    ci_low = max(0, int(rul_wafers - 1.96 * sigma_rul))
    ci_high = int(rul_wafers + 1.96 * sigma_rul)
    
    health_pct = min(max(remaining_depth / (PAD_INITIAL_GROOVE_UM - PAD_CRITICAL_GROOVE_UM) * 100.0, 0.0), 100.0)
    
    return {
        "consumable": "Polishing Pad",
        "current_val": round(current_groove_um, 1),
        "critical_val": PAD_CRITICAL_GROOVE_UM,
        "rul_wafers": int(round(rul_wafers)),
        "ci_95": [ci_low, ci_high],
        "health_pct": round(health_pct, 1),
        "status": "CRIT" if current_groove_um <= PAD_CRITICAL_GROOVE_UM else ("WARN" if current_groove_um <= PAD_WARN_GROOVE_UM else "NORMAL")
    }

def estimate_conditioner_rul(current_hours: float) -> Dict[str, Any]:
    """
    Estimates Remaining Useful Life (RUL) in hours and equivalent wafers for the diamond conditioner.
    """
    remaining_hours = max(CONDITIONER_LIMIT_HOURS - current_hours, 0.0)
    wafers_per_hour = 10.0  # 6 min per wafer
    rul_wafers = int(round(remaining_hours * wafers_per_hour))
    
    ci_low = max(0, int(rul_wafers * 0.90))
    ci_high = int(rul_wafers * 1.10)
    health_pct = min(max(remaining_hours / CONDITIONER_LIMIT_HOURS * 100.0, 0.0), 100.0)
    
    return {
        "consumable": "Diamond Conditioner Disc",
        "current_val": round(current_hours, 1),
        "critical_val": CONDITIONER_LIMIT_HOURS,
        "rul_hours": round(remaining_hours, 1),
        "rul_wafers": rul_wafers,
        "ci_95": [ci_low, ci_high],
        "health_pct": round(health_pct, 1),
        "status": "CRIT" if current_hours >= CONDITIONER_LIMIT_HOURS else ("WARN" if current_hours >= CONDITIONER_WARN_HOURS else "NORMAL")
    }

if __name__ == "__main__":
    print("Pad RUL (Groove 460um, Wafers 450):", estimate_pad_rul(460.0, 450))
    print("Pad RUL (Groove 390um, Wafers 490):", estimate_pad_rul(390.0, 490))
    print("Conditioner RUL (52 hrs):", estimate_conditioner_rul(52.0))
