import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.scenario_builder import build_scenarios

if __name__ == "__main__":
    print("[3/4] Generating 5-day operational scenarios...")
    scenarios = build_scenarios()
    print(f"Generated {len(scenarios)} multi-chamber fab scenarios.")
