#!/usr/bin/env python3
"""
Local test runner for hermes-wind.
Run from the hermes-wind/ directory:

    python test_local.py
"""
import importlib.util
import json
import logging
import os
import sys
import types

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
for _noisy in ("urllib3", "urllib", "http.client"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = "hermes_wind"


def _register_package():
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [_HERE]
    pkg.__package__ = _PKG
    sys.modules[_PKG] = pkg


def _load_module(name):
    path = os.path.join(_HERE, f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"{_PKG}.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = _PKG
    sys.modules[f"{_PKG}.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_register_package()
for _m in ("client", "schemas", "tools"):
    _load_module(_m)

from hermes_wind.tools import (
    handle_wind_check_spot,
    handle_wind_get_forecast,
    handle_wind_list_spots,
    handle_wind_search_spots,
)


def _pretty(result_json: str) -> None:
    try:
        print(json.dumps(json.loads(result_json), indent=2, ensure_ascii=False))
    except Exception:
        print(result_json)


def _section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


if __name__ == "__main__":
    print("hermes-wind local test")
    print("-" * 40)

    _section("Oostvoorne conditions (default)")
    _pretty(handle_wind_check_spot({}))

    _section("Search Oostvoorne")
    _pretty(handle_wind_search_spots({"query": "Oostvoorne"}))

    _section("Forecast Oostvoorne (1 day)")
    _pretty(handle_wind_get_forecast({"spot": "Oostvoorne", "days": 1}))

    _section("List spots matching 'voorn'")
    _pretty(handle_wind_list_spots({"query": "voorn", "limit": 5}))

    print("\n✓ All tests completed.")