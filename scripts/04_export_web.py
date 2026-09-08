import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.scenario_builder import export_all

if __name__ == "__main__":
    print("[4/4] Exporting payload to docs/data.js for GitHub Pages simulator...")
    export_all()
    print("Done! Open docs/index.html in a browser.")
