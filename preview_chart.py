#!/usr/bin/env python3
"""Generate a local wind chart preview for layout iteration."""
import importlib.util
import json
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = "hermes_wind"
_MS_TO_KNOTS = 1.94384


def _bootstrap():
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [_HERE]
    pkg.__package__ = _PKG
    sys.modules[_PKG] = pkg

    for name in ("client", "schemas", "tools", "chart"):
        path = os.path.join(_HERE, f"{name}.py")
        spec = importlib.util.spec_from_file_location(f"{_PKG}.{name}", path)
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = _PKG
        sys.modules[f"{_PKG}.{name}"] = mod
        spec.loader.exec_module(mod)


def _current_wind(winddata: list) -> dict | None:
    if not winddata:
        return None
    latest = winddata[0]
    speed = latest.get("windsnelheidMS")
    return {
        "timestamp": latest.get("tijdstip"),
        "speed_knots": round(speed * _MS_TO_KNOTS, 1) if speed is not None else None,
        "gust_knots": round(latest.get("windstotenMS") * _MS_TO_KNOTS, 1)
        if latest.get("windstotenMS") is not None else None,
        "direction_deg": latest.get("windrichtingGR"),
        "direction_label": latest.get("windrichting"),
    }


if __name__ == "__main__":
    _bootstrap()
    from hermes_wind.client import get_client
    from hermes_wind.chart import render_wind_chart

    client = get_client()
    spot_id = client.default_spot_id()
    detail = client.get_spot_detail(spot_id)

    payload = {
        "spot": {
            "spot_id": detail.get("info", {}).get("stationcode", spot_id),
            "name": detail.get("info", {}).get("spotnaam", "Spot"),
        },
        "current": _current_wind(detail.get("winddata") or []),
        "winddata": detail.get("winddata"),
        "observations": detail.get("observations"),
        "forecast": detail.get("forecast"),
        "tide": [
            {"time": t.get("tijdstip"), "type": t.get("getij"), "hoogte": t.get("hoogte")}
            for t in (detail.get("getij") or [])
        ],
    }

    path = render_wind_chart(payload)
    print(path)