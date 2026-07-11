"""ActueleWind tool handlers — kitesurf wind monitoring."""
import json
import logging
from datetime import datetime

from .client import get_client

logger = logging.getLogger(__name__)

_MS_TO_KNOTS = 1.94384
_MIN_KITE_MS = 6.0   # ~12 kn — workable minimum
_GOOD_KITE_MS = 8.0    # ~16 kn — solid session
_GREAT_KITE_MS = 10.0  # ~19 kn — strong session

_WEATHER_CODES = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Heavy rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
}


# ----------------------------------------------------------------- check fn

def check_wind_available() -> bool:
    return True


def check_chart_available() -> bool:
    try:
        import matplotlib  # noqa: F401
        return True
    except ImportError:
        return False


# ----------------------------------------------------------------- helpers

def _ms_to_knots(ms: float | None) -> float | None:
    if ms is None:
        return None
    return round(ms * _MS_TO_KNOTS, 1)


def _weather_label(code: int | None) -> str | None:
    if code is None:
        return None
    return _WEATHER_CODES.get(code, f"Code {code}")


def _direction_in_range(deg: float | None, min_deg: float, max_deg: float) -> bool | None:
    if deg is None:
        return None
    deg = deg % 360
    min_deg %= 360
    max_deg %= 360
    if min_deg <= max_deg:
        return min_deg <= deg <= max_deg
    return deg >= min_deg or deg <= max_deg


def _wind_rating(speed_ms: float | None) -> str:
    if speed_ms is None:
        return "unknown"
    if speed_ms < 4:
        return "too_light"
    if speed_ms < _MIN_KITE_MS:
        return "marginal"
    if speed_ms < _GOOD_KITE_MS:
        return "rideable"
    if speed_ms < _GREAT_KITE_MS:
        return "good"
    if speed_ms < 14:
        return "great"
    if speed_ms < 18:
        return "strong"
    return "extreme"


def _kitesurf_verdict(
    speed_ms: float | None,
    gust_ms: float | None,
    direction_deg: float | None,
    best_min: float | None,
    best_max: float | None,
    kite_allowed: str | None = None,
) -> dict:
    rating = _wind_rating(speed_ms)
    direction_ok = _direction_in_range(direction_deg, best_min or 0, best_max or 360)
    gust_factor = None
    if speed_ms and gust_ms and speed_ms > 0:
        gust_factor = round(gust_ms / speed_ms, 2)

    issues: list[str] = []
    if kite_allowed and kite_allowed not in ("toegestaan", "allowed"):
        issues.append(f"kite status: {kite_allowed}")
    if rating in ("too_light", "marginal"):
        issues.append("wind too light for kitesurfing")
    if rating in ("strong", "extreme"):
        issues.append("wind very strong — experienced riders only")
    if direction_ok is False:
        issues.append("wind direction not ideal for this spot")
    if gust_factor and gust_factor > 1.6:
        issues.append("gusty conditions")

    if issues:
        if rating in ("too_light", "marginal"):
            session = "no"
        elif rating in ("strong", "extreme") or (gust_factor and gust_factor > 1.8):
            session = "maybe"
        else:
            session = "maybe"
    elif rating in ("rideable", "good", "great"):
        session = "yes"
    elif rating == "marginal" and direction_ok:
        session = "maybe"
    else:
        session = "no"

    return {
        "session_recommended": session,
        "wind_rating": rating,
        "direction_ideal": direction_ok,
        "gust_factor": gust_factor,
        "issues": issues,
    }


def _current_wind(winddata: list) -> dict | None:
    if not winddata:
        return None
    latest = winddata[0]
    speed = latest.get("windsnelheidMS")
    gust = latest.get("windstotenMS")
    return {
        "timestamp": latest.get("tijdstip"),
        "speed_ms": speed,
        "speed_knots": _ms_to_knots(speed),
        "gust_ms": gust,
        "gust_knots": _ms_to_knots(gust),
        "direction_deg": latest.get("windrichtingGR"),
        "direction_label": latest.get("windrichting"),
        "temperature_c": latest.get("temperatuurGC"),
        "weather": latest.get("icoonactueel"),
        "rain_mm_h": latest.get("regenMMPU"),
    }


def _spot_meta_from_detail(detail: dict) -> dict:
    info = detail.get("info") or {}
    return {
        "spot_id": info.get("stationcode"),
        "name": info.get("spotnaam"),
        "latitude": info.get("latGraden"),
        "longitude": info.get("lonGraden"),
        "reliability_pct": info.get("betrouwbaarheid"),
        "virtual_spot": bool(info.get("virtualspot")),
    }


def _spot_meta_from_overview(spot_id: int) -> dict:
    overview = get_client().get_spot_overview()
    for spot in overview["spots"]:
        if spot["spot_id"] == spot_id:
            return spot
    return {"spot_id": spot_id}


def _resolve_spot_id(args: dict) -> tuple[int | None, dict | None]:
    client = get_client()
    query = (args.get("spot") or "").strip()
    if query:
        match = client.resolve_spot(query)
        if not match:
            return None, {"error": f"Spot '{query}' not found. Use wind_search_spots to look up names."}
        if match.get("ambiguous"):
            return None, {
                "error": f"Multiple spots match '{query}'",
                "matches": match.get("matches", []),
            }
        return int(match["spot_id"]), None
    return client.default_spot_id(), None


def _summarize_forecast_hours(forecast_data: dict, hours: int = 12) -> list[dict]:
    model = (forecast_data.get("forecast") or {}).get("dwd_icon_d2") or []
    result = []
    for entry in model[:hours]:
        speed = entry.get("wind_speed_10m")
        gust = entry.get("wind_gusts_10m")
        result.append({
            "time": entry.get("valid_time"),
            "speed_ms": speed,
            "speed_knots": _ms_to_knots(speed),
            "gust_ms": gust,
            "gust_knots": _ms_to_knots(gust),
            "direction_deg": entry.get("wind_direction_10m"),
            "temperature_c": entry.get("temperature_2m"),
            "precipitation_mm": entry.get("precipitation"),
            "weather": _weather_label(entry.get("weather_code")),
            "wave_height_m": entry.get("golfhoogteM"),
        })
    return result


def _best_windows(forecast_hours: list[dict], best_min: float, best_max: float) -> list[dict]:
    windows = []
    for entry in forecast_hours:
        speed = entry.get("speed_ms")
        if speed is None or speed < _MIN_KITE_MS:
            continue
        direction = entry.get("direction_deg")
        if _direction_in_range(direction, best_min, best_max) is False:
            continue
        windows.append({
            "time": entry.get("time"),
            "speed_knots": entry.get("speed_knots"),
            "gust_knots": entry.get("gust_knots"),
            "direction_deg": direction,
            "rating": _wind_rating(speed),
        })
    return windows[:6]


# ----------------------------------------------------------------- handlers

def handle_wind_check_spot(args: dict, **_) -> str:
    """Comprehensive kitesurf conditions check — ideal for cron monitoring."""
    try:
        spot_id, err = _resolve_spot_id(args)
        if err:
            return json.dumps(err)

        client = get_client()
        detail = client.get_spot_detail(spot_id)
        water = client.get_water_temp(spot_id)
        waves = client.get_waves(spot_id)
        forecast_days = int(args.get("forecast_days") or 1)
        forecast = client.get_forecast(spot_id, days=forecast_days)
        weather_text = client.get_weather_text(spot_id)

        meta = _spot_meta_from_detail(detail)
        overview_meta = _spot_meta_from_overview(spot_id)
        current = _current_wind(detail.get("winddata") or [])

        best_min = overview_meta.get("wind_best_min_gr") or detail.get("info", {}).get("windrichtingVan") or 0
        best_max = overview_meta.get("wind_best_max_gr") or detail.get("info", {}).get("windrichtingTot") or 360

        verdict = _kitesurf_verdict(
            current.get("speed_ms") if current else None,
            current.get("gust_ms") if current else None,
            current.get("direction_deg") if current else None,
            best_min,
            best_max,
            overview_meta.get("kite_allowed"),
        )

        forecast_hours = _summarize_forecast_hours(forecast, hours=int(args.get("forecast_hours") or 12))
        best_windows = _best_windows(forecast_hours, best_min, best_max)

        zon = detail.get("zon") or {}
        tide = detail.get("getij") or []

        payload = {
            "spot": meta,
            "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "current": current,
            "kitesurf": verdict,
            "water": {
                "temperature_c": water.get("watertemperatuurGC"),
                "last_update": water.get("lastUpdate"),
                "stations": water.get("stations", []),
            },
            "waves": {
                "height_m": waves.get("golfhoogteM"),
                "period_s": waves.get("golfperiodeS"),
                "direction_deg": waves.get("golfrichtingGR"),
                "last_update": waves.get("lastUpdate"),
            },
            "sun": {
                "sunrise": zon.get("opkomst"),
                "sunset": zon.get("onder"),
            },
            "tide": [
                {
                    "time": t.get("tijdstip"),
                    "type": t.get("getij"),
                    "height_cm": t.get("hoogte"),
                }
                for t in tide[:6]
            ],
            "forecast_next_hours": forecast_hours,
            "best_kite_windows": best_windows,
            "weather_summary": (weather_text.get("verwachting_vandaag") or {}).get("samenvatting"),
            "url": f"https://actuelewind.nl/spot/{spot_id}",
        }
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        logger.error("wind_check_spot: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_wind_get_forecast(args: dict, **_) -> str:
    try:
        spot_id, err = _resolve_spot_id(args)
        if err:
            return json.dumps(err)

        days = int(args.get("days") or 2)
        client = get_client()
        detail = client.get_spot_detail(spot_id)
        forecast = client.get_forecast(spot_id, days=days)
        meta = _spot_meta_from_detail(detail)

        hours = days * 24
        forecast_hours = _summarize_forecast_hours(forecast, hours=hours)

        return json.dumps({
            "spot": meta,
            "days": days,
            "resolution": forecast.get("resolution"),
            "forecast": forecast_hours,
            "url": f"https://actuelewind.nl/spot/{spot_id}",
        }, ensure_ascii=False)
    except Exception as exc:
        logger.error("wind_get_forecast: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_wind_search_spots(args: dict, **_) -> str:
    try:
        query = (args.get("query") or "").strip()
        if not query:
            return json.dumps({"error": "query is required"})

        client = get_client()
        match = client.resolve_spot(query)
        if not match:
            overview = client.get_spot_overview()
            partial = [
                s for s in overview["spots"]
                if query.casefold() in s["name"].casefold()
            ][: int(args.get("limit") or 10)]
            return json.dumps({"query": query, "matches": partial, "count": len(partial)})

        if match.get("ambiguous"):
            return json.dumps({
                "query": query,
                "ambiguous": True,
                "matches": match.get("matches", []),
                "count": len(match.get("matches", [])),
            })

        spot_id = int(match["spot_id"])
        detail = client.get_spot_detail(spot_id)
        meta = _spot_meta_from_detail(detail)
        current = _current_wind(detail.get("winddata") or [])
        return json.dumps({
            "query": query,
            "match": meta,
            "current_wind_knots": current.get("speed_knots") if current else None,
            "url": f"https://actuelewind.nl/spot/{spot_id}",
        }, ensure_ascii=False)
    except Exception as exc:
        logger.error("wind_search_spots: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_wind_chart_spot(args: dict, **_) -> str:
    try:
        from .chart import render_wind_chart
    except ImportError:
        from chart import render_wind_chart

    try:
        spot_id, err = _resolve_spot_id(args)
        if err:
            return json.dumps(err)

        client = get_client()
        detail = client.get_spot_detail(spot_id)
        meta = _spot_meta_from_detail(detail)
        current = _current_wind(detail.get("winddata") or [])

        payload = {
            "spot": meta,
            "current": current,
            "winddata": detail.get("winddata"),
            "observations": detail.get("observations"),
            "forecast": detail.get("forecast"),
            "tide": [
                {
                    "time": t.get("tijdstip"),
                    "type": t.get("getij"),
                    "hoogte": t.get("hoogte"),
                }
                for t in (detail.get("getij") or [])
            ],
        }
        chart_path = render_wind_chart(payload)
        return json.dumps({
            "spot": meta,
            "chart_path": chart_path,
            "signal_message": f"MEDIA:{chart_path}",
            "url": f"https://actuelewind.nl/spot/{spot_id}",
        }, ensure_ascii=False)
    except Exception as exc:
        logger.error("wind_chart_spot: %s", exc)
        return json.dumps({"error": str(exc)})


def handle_wind_list_spots(args: dict, **_) -> str:
    try:
        query = (args.get("query") or "").strip().casefold()
        limit = int(args.get("limit") or 20)
        overview = get_client().get_spot_overview()
        spots = overview["spots"]
        if query:
            spots = [s for s in spots if query in s["name"].casefold()]
        spots = spots[:limit]
        return json.dumps({"spots": spots, "count": len(spots)}, ensure_ascii=False)
    except Exception as exc:
        logger.error("wind_list_spots: %s", exc)
        return json.dumps({"error": str(exc)})