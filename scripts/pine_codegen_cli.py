from __future__ import annotations
import json, argparse, pathlib
from agents.pine_codegen import generate_pine

def main():
    ap = argparse.ArgumentParser("KTW Pine v5 codegen CLI")
    ap.add_argument("--spec-json", required=True)
    ap.add_argument("--out", default="docs/generated/leader.pine")
    args = ap.parse_args()
    spec = json.load(open(args.spec_json))
    code = generate_pine(spec)
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(code, encoding="utf-8")
    print(f"OK: wrote {args.out}")

if __name__ == "__main__":
    main()
