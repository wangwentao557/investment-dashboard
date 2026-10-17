#!/usr/bin/env python3
"""Compatibility entry point; canonical implementation lives at ../account_import.py."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "account_import.py"), run_name="__main__")
