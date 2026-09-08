"""
virtual_metrology.py
Virtual Metrology (VM) models for CMP Material Removal Rate (MRR) prediction.
Implements:
1. Baseline: Ridge Regression
2. Baseline: Random Forest Regressor
3. Advanced / Deep: Multi-Layer Neural Network (MLP / 1D-Feature Network)
Evaluates RMSE, MAE, R^2 with strict temporal validation (zero future leakage).
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

# Ensure src is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

FEATURE_COLS = [
    "PRESS_DOWNFORCE_Z1", "PRESS_DOWNFORCE_Z2", "PRESS_DOWNFORCE_Z3",
    "PRESS_RETAINING_RING", "ROTATION_TABLE_RPM", "ROTATION_HEAD_RPM",
    "FLOW_RATE_SLURRY", "CURRENT_TABLE_MOTOR", "TEMP_PAD",
    "CONDITIONER_DOWNFORCE", "USAGE_OF_POLISHING_TABLE",
    "USAGE_OF_DRESSER", "PAD_GROOVE_DEPTH_UM"
]

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Adds domain-specific physical features based on CMP tribology."""
    data = df.copy()
    p_avg = (data["PRESS_DOWNFORCE_Z1"] + data["PRESS_DOWNFORCE_Z2"] + data["PRESS_DOWNFORCE_Z3"]) / 3.0
    v_avg = (data["ROTATION_TABLE_RPM"] * 0.52 + data["ROTATION_HEAD_RPM"] * 0.48) * 0.035
    
    data["PRESS_AVG"] = p_avg
    data["VEL_AVG"] = v_avg
    data["PRESTON_PV"] = p_avg * v_avg
    data["FRIC_POWER"] = data["CURRENT_TABLE_MOTOR"] * v_avg
    
    # One-hot encoding for Stage and Chamber
    stage_dummies = pd.get_dummies(data["STAGE"], prefix="STAGE", drop_first=False)
    chamber_dummies = pd.get_dummies(data["CHAMBER"], prefix="CHAMBER", drop_first=False)
    
    for col in stage_dummies.columns:
        data[col] = stage_dummies[col].astype(float)
    for col in chamber_dummies.columns:
        data[col] = chamber_dummies[col].astype(float)
        
    return data

def prepare_xy(train_df: pd.DataFrame, val_df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list, StandardScaler]:
    df_train = engineer_features(train_df)
    df_val = engineer_features(val_df)
    
    extra_cols = ["PRESS_AVG", "VEL_AVG", "PRESTON_PV", "FRIC_POWER"]
    dummy_cols = [c for c in df_train.columns if c.startswith("STAGE_") or c.startswith("CHAMBER_")]
    all_feature_cols = FEATURE_COLS + extra_cols + dummy_cols
    
    for col in dummy_cols:
        if col not in df_val.columns:
            df_val[col] = 0.0
            
    X_train_raw = df_train[all_feature_cols].values
    y_train = df_train["RemovalRate"].values
    
    X_val_raw = df_val[all_feature_cols].values
    y_val = df_val["RemovalRate"].values
    
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train_raw)
    X_val = scaler.transform(X_val_raw)
    
    return X_train, y_train, X_val, y_val, all_feature_cols, scaler

def evaluate_predictions(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    r2 = float(r2_score(y_true, y_pred))
    return {"rmse": round(rmse, 2), "mae": round(mae, 2), "r2": round(r2, 4)}

def train_and_compare_models(train_df: pd.DataFrame, val_df: pd.DataFrame) -> Dict[str, Any]:
    X_train, y_train, X_val, y_val, features, scaler = prepare_xy(train_df, val_df)
    
    models = {
        "Baseline_Ridge": Ridge(alpha=1.0),
        "Baseline_RandomForest": RandomForestRegressor(n_estimators=60, max_depth=10, random_state=42, n_jobs=-1),
        "Advanced_MLP": MLPRegressor(hidden_layer_sizes=(64, 32), activation="relu", max_iter=300, random_state=42, early_stopping=True)
    }
    
    results = {}
    best_model_name = "Advanced_MLP"
    best_r2 = -1.0
    trained_models = {}
    
    for name, model in models.items():
        model.fit(X_train, y_train)
        y_train_pred = model.predict(X_train)
        y_val_pred = model.predict(X_val)
        
        train_metrics = evaluate_predictions(y_train, y_train_pred)
        val_metrics = evaluate_predictions(y_val, y_val_pred)
        
        results[name] = {
            "train": train_metrics,
            "val": val_metrics,
            "y_val_actual": [round(float(v), 1) for v in y_val[:120]],
            "y_val_pred": [round(float(v), 1) for v in y_val_pred[:120]]
        }
        trained_models[name] = model
        
        if val_metrics["r2"] > best_r2:
            best_r2 = val_metrics["r2"]
            best_model_name = name
            
    summary = {
        "best_model": best_model_name,
        "features": features,
        "comparison": results
    }
    
    with open("data/vm_evaluation.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        
    return summary

if __name__ == "__main__":
    from src.phm_data import load_cmp_data, get_temporal_split
    df, is_synth = load_cmp_data()
    train_df, val_df = get_temporal_split(df)
    eval_results = train_and_compare_models(train_df, val_df)
    
    print("\n--- Virtual Metrology Benchmark Results ---")
    for m_name, m_data in eval_results["comparison"].items():
        v = m_data["val"]
        print(f"[{m_name}] Val RMSE: {v['rmse']:.2f} A/min | MAE: {v['mae']:.2f} A/min | R²: {v['r2']:.4f}")
    print(f"\nBest Selected Model: {eval_results['best_model']}")
