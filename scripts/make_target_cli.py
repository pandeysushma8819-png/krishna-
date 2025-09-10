from __future__ import annotations
import argparse, json, importlib.util
from pathlib import Path
from typing import Dict, Any, List

def load_module_from_path(path: str):
    spec = importlib.util.spec_from_file_location("user_strategy", path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    return mod

def main():
    ap = argparse.ArgumentParser(description="Generate target.json from custom strategy")
    ap.add_argument("--bars-json", required=True)
    ap.add_argument("--strategy", default="strategies/my_strategy.py")
    ap.add_argument("--params", default="{}")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    bars: List[dict] = json.load(open(a.bars_json, "r"))
    mod = load_module_from_path(a.strategy)
    params: Dict[str, Any] = json.loads(a.params)
    target: Dict[str,int] = mod.compute_positions(bars, params)
    Path(a.out).write_text(json.dumps(target, separators=(",",":")), encoding="utf-8")
    print(f"OK: wrote {a.out} rows={len(target)}")

if __name__ == "__main__":
    main()
