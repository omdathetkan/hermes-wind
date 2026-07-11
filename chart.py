"""Compact wind chart — measurements left, forecast right, tide strip below."""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

_MS_TO_KNOTS = 1.94384

# Landscape-ish — readable on phone without excess height
FIG_W, FIG_H, DPI = 7.0, 3.4, 200

# Measured = blue, forecast = amber — high contrast split
BG = "#f3f5f7"
MEAS_FILL = "#4FC3F7"
MEAS_LINE = "#01579B"
MEAS_BG = "#E1F5FE"
FCST_FILL = "#FFB74D"
FCST_LINE = "#E65100"
FCST_BG = "#FFF3E0"
NOW_LINE = "#263238"
GRID = "#cfd8dc"
INK = "#263238"
MUTED = "#607d8b"
TIDE_LINE = "#455a64"
TIDE_FILL = "#90a4ae"
TIDE_HIGH = "#01579B"
TIDE_LOW = "#E65100"
KITE_BAND = "#2e7d32"
KITE_BAND_ALPHA = 0.10

WIND_SPEED_LW = 1.35
WIND_GUST_LW = 0.75
TIDE_LW = 1.0


def _chart_dir() -> Path:
    base = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
    out = base / "media" / "wind"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _kn(ms: float | None) -> float | None:
    if ms is None:
        return None
    return ms * _MS_TO_KNOTS


def _wind_rows(rows: list[dict], *, measured: bool) -> list[dict]:
    out: list[dict] = []
    for row in rows or []:
        ts = _parse_time(row.get("tijdstip"))
        speed = _kn(row.get("windsnelheidMS"))
        if ts is None or speed is None:
            continue
        direction = row.get("windrichtingGR")
        out.append({
            "time": ts,
            "speed_knots": speed,
            "gust_knots": _kn(row.get("windstotenMS")),
            "direction_deg": float(direction) if direction is not None else None,
            "measured": measured,
        })
    out.sort(key=lambda r: r["time"])
    return out


def _tide_points(getij: list[dict]) -> list[tuple[datetime, float]]:
    points: list[tuple[datetime, float]] = []
    for entry in getij or []:
        ts = _parse_time(entry.get("tijdstip") or entry.get("time"))
        height = entry.get("hoogte")
        if height is None:
            height = entry.get("height_cm")
        if ts is None or height is None:
            continue
        points.append((ts, float(height)))
    points.sort(key=lambda p: p[0])
    return points


def _hourly_wind_directions(
    rows: list[dict],
    t_min: datetime,
    t_max: datetime,
) -> list[tuple[datetime, float, bool]]:
    """Sample wind direction at each whole hour (nearest row within 30 min)."""
    with_dir = [r for r in rows if r.get("direction_deg") is not None]
    if not with_dir:
        return []

    cur = t_min.replace(minute=0, second=0, microsecond=0)
    if cur < t_min:
        cur += timedelta(hours=1)

    samples: list[tuple[datetime, float, bool]] = []
    while cur <= t_max:
        nearest = min(with_dir, key=lambda r: abs((r["time"] - cur).total_seconds()))
        if abs((nearest["time"] - cur).total_seconds()) <= 1800:
            samples.append((cur, nearest["direction_deg"], nearest["measured"]))
        cur += timedelta(hours=1)
    return samples


def _draw_wind_arrow(ax, x: datetime, y: float, from_deg: float, color: str) -> None:
    """Fixed-size arrow (screen points) pointing where the wind blows."""
    blow_deg = (from_deg + 180) % 360
    rad = math.radians(90 - blow_deg)
    length = 9.0
    dx = length * math.cos(rad)
    dy = length * math.sin(rad)
    ax.annotate(
        "",
        xy=(x, y),
        xytext=(-dx, -dy),
        textcoords="offset points",
        arrowprops={
            "arrowstyle": "-|>",
            "color": color,
            "lw": 1.0,
            "shrinkA": 0,
            "shrinkB": 0,
            "mutation_scale": 8,
        },
        zorder=8,
        annotation_clip=False,
    )


def _interp_tide_segment(
    t0: datetime,
    h0: float,
    t1: datetime,
    h1: float,
    seg_start: datetime,
    seg_end: datetime,
    step: timedelta,
) -> tuple[list[datetime], list[float]]:
    """Smooth cosine half-wave between two HW/LW events (hits both endpoints)."""
    times: list[datetime] = []
    heights: list[float] = []
    dur = (t1 - t0).total_seconds()
    if dur <= 0:
        return times, heights

    cur = seg_start
    while cur <= seg_end:
        progress = (cur - t0).total_seconds() / dur
        progress = max(0.0, min(1.0, progress))
        h = h0 + (h1 - h0) * (1 - math.cos(math.pi * progress)) / 2
        times.append(cur)
        heights.append(h)
        cur += step
    return times, heights


def _tide_curve(getij: list[dict], t_min: datetime, t_max: datetime) -> tuple[list[datetime], list[float]]:
    points = _tide_points(getij)
    if len(points) < 2:
        return [], []

    step = timedelta(minutes=8)
    times: list[datetime] = []
    heights: list[float] = []

    for i in range(len(points) - 1):
        t0, h0 = points[i]
        t1, h1 = points[i + 1]
        if t1 < t_min or t0 > t_max:
            continue
        seg_t, seg_h = _interp_tide_segment(
            t0, h0, t1, h1,
            max(t0, t_min), min(t1, t_max),
            step,
        )
        times.extend(seg_t)
        heights.extend(seg_h)

    if not times:
        return [], []

    combined = sorted(zip(times, heights), key=lambda p: p[0])
    return [t for t, _ in combined], [h for _, h in combined]


def render_wind_chart(payload: dict) -> str:
    """Render compact wind+tide PNG. Returns absolute file path."""
    spot = payload.get("spot") or {}
    spot_name = spot.get("name") or "Spot"
    spot_id = spot.get("spot_id") or "spot"

    measured = _wind_rows(payload.get("winddata") or payload.get("observations"), measured=True)
    forecast = _wind_rows(payload.get("forecast"), measured=False)
    tides = payload.get("tide") or payload.get("getij") or []

    if not measured and not forecast:
        raise ValueError("No wind series to chart")

    now = _parse_time((payload.get("current") or {}).get("timestamp"))
    if now is None and measured:
        now = measured[-1]["time"]
    if now is None:
        now = datetime.now().replace(second=0, microsecond=0)

    # Split at now: measurements ≤ now, forecast ≥ now
    obs = [r for r in measured if r["time"] <= now]
    fcst = [r for r in forecast if r["time"] >= now]

    # Ensure the lines meet at now — bridge with latest measurement if needed
    if obs and fcst and obs[-1]["time"] < now < fcst[0]["time"]:
        last = obs[-1]
        fcst = [{"time": now, "speed_knots": last["speed_knots"],
                 "gust_knots": last.get("gust_knots"),
                 "direction_deg": last.get("direction_deg"),
                 "measured": False}] + fcst
    elif obs and not fcst:
        fcst = [dict(obs[-1], measured=False)]

    all_times = [r["time"] for r in obs + fcst]
    t_min, t_max = min(all_times), max(all_times)
    pad = timedelta(minutes=20)
    t_min -= pad
    t_max += pad

    all_speeds = [r["speed_knots"] for r in obs + fcst]
    all_gusts = [r["gust_knots"] for r in obs + fcst if r.get("gust_knots") is not None]
    y_max = max(all_speeds + all_gusts + [16])
    y_max = int(math.ceil(y_max / 4.0) * 4 + 4)

    generated_at = datetime.now().replace(second=0, microsecond=0)

    fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor=BG)
    gs = fig.add_gridspec(2, 1, height_ratios=[4.2, 1], hspace=0.06,
                          left=0.10, right=0.98, top=0.86, bottom=0.10)

    fig.text(
        0.10, 0.94,
        f"{spot_name}  ·  {generated_at.strftime('%d %b %Y %H:%M')}",
        fontsize=9, fontweight="bold", color=INK, va="top",
    )

    ax = fig.add_subplot(gs[0])
    tax = fig.add_subplot(gs[1], sharex=ax)

    # Background tint: measured left / forecast right
    ax.axvspan(t_min, now, color=MEAS_BG, zorder=0)
    ax.axvspan(now, t_max, color=FCST_BG, zorder=0)
    ax.axvline(now, color=NOW_LINE, lw=1.0, zorder=6)
    ax.axhline(12, color=KITE_BAND, lw=0.6, alpha=0.35, zorder=0)

    # Kite band
    ax.axhspan(12, min(25, y_max), color=KITE_BAND, alpha=KITE_BAND_ALPHA, zorder=0)

    def _plot_series(series: list[dict], fill: str, line: str) -> None:
        if not series:
            return
        times = [r["time"] for r in series]
        speeds = [r["speed_knots"] for r in series]
        ax.fill_between(times, speeds, 0, color=fill, alpha=0.50, zorder=2)
        ax.plot(times, speeds, color=line, lw=WIND_SPEED_LW, solid_capstyle="round", zorder=3)
        gusts = [(r["time"], r["gust_knots"]) for r in series if r.get("gust_knots") is not None]
        if gusts:
            gt, gv = zip(*gusts)
            ax.plot(
                gt, gv, color=line, lw=WIND_GUST_LW,
                linestyle=(0, (2.5, 2.5)), alpha=0.80, zorder=3,
            )

    _plot_series(obs, MEAS_FILL, MEAS_LINE)
    _plot_series(fcst, FCST_FILL, FCST_LINE)

    ax.set_xlim(t_min, t_max)
    ax.set_ylim(0, y_max)
    ax.set_ylabel("kn", fontsize=8, color=INK, labelpad=2)
    ax.tick_params(axis="y", labelsize=7, colors=MUTED, length=2, pad=1)
    ax.tick_params(axis="x", labelbottom=False)
    ax.grid(True, axis="y", color=GRID, lw=0.5, alpha=0.8)
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    ax.spines["left"].set_color(GRID)

    # Hourly wind-direction arrows along the top edge
    dir_rows = obs + fcst
    arrow_y = y_max - 0.6
    for hour, deg, is_meas in _hourly_wind_directions(dir_rows, t_min, t_max):
        color = MEAS_LINE if is_meas else FCST_LINE
        _draw_wind_arrow(ax, hour, arrow_y, deg, color)

    ax.text(0.02, 0.92, "meting", transform=ax.transAxes, fontsize=6.5,
            color=MEAS_LINE, va="top", fontweight="bold")
    ax.text(0.98, 0.92, "voorspelling", transform=ax.transAxes, fontsize=6.5,
            color=FCST_LINE, va="top", ha="right", fontweight="bold")
    ax.text(now, y_max * 0.98, "nu", fontsize=6.5, color=NOW_LINE,
            ha="center", va="top", zorder=7)

    # Tide sub-chart
    tide_t, tide_h = _tide_curve(tides, t_min, t_max)
    if tide_t:
        tax.fill_between(tide_t, tide_h, 0, where=[h >= 0 for h in tide_h],
                         color=TIDE_FILL, alpha=0.25, interpolate=True)
        tax.fill_between(tide_t, tide_h, 0, where=[h < 0 for h in tide_h],
                         color=TIDE_FILL, alpha=0.15, interpolate=True)
        tax.plot(tide_t, tide_h, color=TIDE_LINE, lw=TIDE_LW, solid_capstyle="round")
        tax.axhline(0, color=GRID, lw=0.6)

    for entry in tides:
        ts = _parse_time(entry.get("tijdstip") or entry.get("time"))
        height = entry.get("hoogte") or entry.get("height_cm")
        if ts is None or height is None or not (t_min <= ts <= t_max):
            continue
        kind = (entry.get("getij") or entry.get("type") or "").lower()
        is_high = "hoog" in kind
        color = TIDE_HIGH if is_high else TIDE_LOW
        marker = "^" if is_high else "v"
        tax.axvline(ts, color=color, lw=0.7, ls=":", alpha=0.45, zorder=2)
        tax.scatter(
            [ts], [height], s=36, color=color, marker=marker,
            zorder=5, edgecolors="white", linewidths=0.5,
        )
        label = "HW" if is_high else "LW"
        tax.annotate(
            label, (ts, height),
            textcoords="offset points", xytext=(0, 7 if is_high else -10),
            ha="center", va="bottom" if is_high else "top",
            fontsize=5.5, fontweight="bold", color=color, zorder=6,
        )

    if tide_h:
        pad = 15
        tax.set_ylim(min(tide_h) - pad, max(tide_h) + pad)

    tax.set_ylabel("cm", fontsize=7, color=MUTED, labelpad=1)
    tax.tick_params(axis="y", labelsize=6, colors=MUTED, length=2, pad=1)
    tax.tick_params(axis="x", labelsize=7, colors=MUTED, length=2, pad=1, rotation=0)
    tax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    tax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    tax.spines[["top", "right"]].set_visible(False)
    tax.spines[["left", "bottom"]].set_color(GRID)
    tax.grid(True, axis="y", color=GRID, lw=0.4, alpha=0.6)

    day = now.strftime("%Y-%m-%d")
    out_path = _chart_dir() / f"{spot_id}-{day}.png"
    fig.savefig(out_path, dpi=DPI, facecolor=BG, pad_inches=0.04)
    plt.close(fig)
    return str(out_path.resolve())