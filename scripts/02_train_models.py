import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.phm_data import load_cmp_data, get_temporal_split
from src.virtual_metrology import train_and_compare_models

if __name__ == "__main__":
    print("[2/4] Training Virtual Metrology models...")
    df, _ = load_cmp_data()
    train_df, val_df = get_temporal_split(df)
    results = train_and_compare_models(train_df, val_df)
    for m_name, m_data in results["comparison"].items():
        v = m_data["val"]
        print(f"  {m_name:<24} | Val RMSE: {v['rmse']:>6.2f} A/min | MAE: {v['mae']:>6.2f} A/min | R2: {v['r2']:>6.4f}")
