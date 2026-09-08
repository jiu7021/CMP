import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.phm_data import load_cmp_data, get_temporal_split

if __name__ == "__main__":
    print("[1/4] Preparing CMP dataset...")
    df, is_synth = load_cmp_data()
    train_df, val_df = get_temporal_split(df)
    print(f"Dataset ready. Total: {len(df)} wafers, Train: {len(train_df)}, Val: {len(val_df)}, Synthetic: {is_synth}")
