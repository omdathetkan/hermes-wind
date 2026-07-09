"""Hermes Wind plugin — kitesurf wind monitoring via actuelewind.nl."""
import logging

logger = logging.getLogger(__name__)


def register(ctx):
    from .schemas import (
        WIND_CHECK_SPOT_SCHEMA,
        WIND_GET_FORECAST_SCHEMA,
        WIND_LIST_SPOTS_SCHEMA,
        WIND_SEARCH_SPOTS_SCHEMA,
    )
    from .tools import (
        check_wind_available,
        handle_wind_check_spot,
        handle_wind_get_forecast,
        handle_wind_list_spots,
        handle_wind_search_spots,
    )

    _kw = {"check_fn": check_wind_available, "toolset": "wind"}

    ctx.register_tool(
        name="wind_check_spot",
        schema=WIND_CHECK_SPOT_SCHEMA,
        handler=lambda a, **k: handle_wind_check_spot(a, **k),
        **_kw,
    )
    ctx.register_tool(
        name="wind_get_forecast",
        schema=WIND_GET_FORECAST_SCHEMA,
        handler=lambda a, **k: handle_wind_get_forecast(a, **k),
        **_kw,
    )
    ctx.register_tool(
        name="wind_search_spots",
        schema=WIND_SEARCH_SPOTS_SCHEMA,
        handler=lambda a, **k: handle_wind_search_spots(a, **k),
        **_kw,
    )
    ctx.register_tool(
        name="wind_list_spots",
        schema=WIND_LIST_SPOTS_SCHEMA,
        handler=lambda a, **k: handle_wind_list_spots(a, **k),
        **_kw,
    )

    logger.info("hermes-wind loaded (4 tools, default spot: Oostvoorne)")