"""ActueleWind.nl API client — wind, weather, and water data for kitesurf spots."""
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_API_BASE = "https://actuelewind.nl/api"
_USER_AGENT = "Mozilla/5.0 (compatible; hermes-wind/1.0)"
_DEFAULT_SPOT_ID = 9983  # Oostvoorne
_DEFAULT_SPOT_NAME = "Oostvoorne"
_OVERVIEW_TTL = 300  # seconds


def _urlopen(req: urllib.request.Request, timeout: int = 15):
    host = req.host if hasattr(req, "host") else ""
    if host:
        if ":" in host:
            h, p = host.rsplit(":", 1)
            req.host = h.rstrip(".") + ":" + p
        else:
            req.host = host.rstrip(".")
    return urllib.request.urlopen(req, timeout=timeout)


class ActueleWindClient:
    def __init__(self):
        self._lock = threading.Lock()
        self._overview: dict | None = None
        self._overview_expiry: float = 0.0

    # ------------------------------------------------------------------ config

    def default_spot_id(self) -> int:
        raw = os.environ.get("WIND_DEFAULT_SPOT", "").strip()
        if not raw:
            return _DEFAULT_SPOT_ID
        if raw.isdigit():
            return int(raw)
        match = self.resolve_spot(raw)
        return int(match["spot_id"]) if match else _DEFAULT_SPOT_ID

    # ----------------------------------------------------------- HTTP helpers

    def _request(self, path: str, spot_id: int | None = None, params: dict | None = None) -> dict:
        query = dict(params or {})
        # Cache-buster query param (site uses timestamp-style keys)
        query[str(int(time.time() * 1000))] = ""
        url = _API_BASE + path
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)

        referer = "https://actuelewind.nl/"
        if spot_id is not None:
            referer = f"https://actuelewind.nl/spot/{spot_id}"

        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", _USER_AGENT)
        req.add_header("Accept", "*/*")
        req.add_header("Referer", referer)

        try:
            with _urlopen(req) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise RuntimeError(f"ActueleWind {path} failed ({e.code}): {detail}") from e

    # ------------------------------------------------------------ API methods

    def get_spot_overview(self, force: bool = False) -> dict:
        with self._lock:
            if not force and self._overview and time.time() < self._overview_expiry:
                return self._overview

        data = self._request("/getSpotOverview.php")
        wind = data.get("wind") or {}
        spots: list[dict] = []
        if isinstance(wind, dict):
            for spot_id, entry in wind.items():
                info = (entry or {}).get("windspot") or {}
                if info.get("spotnaam"):
                    spots.append({
                        "spot_id": int(info.get("stationcode") or spot_id),
                        "name": info.get("spotnaam"),
                        "latitude": info.get("latGraden"),
                        "longitude": info.get("lonGraden"),
                        "water_type": info.get("watertype"),
                        "reliability": info.get("betrouwbaarheid"),
                        "kite_allowed": ((info.get("sporten") or {}).get("kite") or {}).get("status"),
                        "wind_best_min_gr": info.get("windBestMinGr"),
                        "wind_best_max_gr": info.get("windBestMaxGr"),
                    })

        overview = {"spots": spots, "count": len(spots), "fetched_at": time.time()}
        with self._lock:
            self._overview = overview
            self._overview_expiry = time.time() + _OVERVIEW_TTL
        return overview

    def resolve_spot(self, query: str) -> dict | None:
        q = (query or "").strip().casefold()
        if not q:
            return None
        if q.isdigit():
            return {"spot_id": int(q), "name": None, "matched_by": "id"}

        overview = self.get_spot_overview()
        exact = [s for s in overview["spots"] if s["name"].casefold() == q]
        if exact:
            s = exact[0]
            return {"spot_id": s["spot_id"], "name": s["name"], "matched_by": "exact"}

        partial = [s for s in overview["spots"] if q in s["name"].casefold()]
        if len(partial) == 1:
            s = partial[0]
            return {"spot_id": s["spot_id"], "name": s["name"], "matched_by": "partial"}
        if len(partial) > 1:
            return {
                "ambiguous": True,
                "matches": [{"spot_id": s["spot_id"], "name": s["name"]} for s in partial[:10]],
            }
        return None

    def get_spot_detail(self, spot_id: int) -> dict:
        return self._request("/getSpotDetail.php", spot_id=spot_id, params={"id": spot_id})

    def get_water_temp(self, spot_id: int) -> dict:
        return self._request("/getSpotWatertemp.php", spot_id=spot_id, params={"spot": spot_id})

    def get_waves(self, spot_id: int) -> dict:
        return self._request("/getSpotGolf.php", spot_id=spot_id, params={"spot": spot_id})

    def get_forecast(self, spot_id: int, days: int = 2) -> dict:
        days = max(1, min(int(days), 7))
        return self._request(
            "/getForecast.php",
            spot_id=spot_id,
            params={"spot": spot_id, "model": "dwd_icon_d2", "days": days},
        )

    def get_weather_text(self, spot_id: int) -> dict:
        return self._request("/getVoorspelling.php", spot_id=spot_id, params={"spot": spot_id})


# ---------------------------------------------------------------- singleton

_client: ActueleWindClient | None = None
_client_lock = threading.Lock()


def get_client() -> ActueleWindClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = ActueleWindClient()
        return _client