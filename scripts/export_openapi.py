#!/usr/bin/env python3
"""Export the TrustShield FastAPI OpenAPI spec to docs/openapi.yaml.

Usage:
    python scripts/export_openapi.py
"""

import sys
from pathlib import Path

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import yaml  # pyyaml

from app.main import app

OUT = Path(__file__).resolve().parent.parent / "docs" / "openapi.yaml"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    spec = app.openapi()

    with open(OUT, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"OpenAPI spec written to {OUT}")


if __name__ == "__main__":
    main()
