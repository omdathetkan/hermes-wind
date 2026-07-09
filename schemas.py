"""JSON schemas for all ActueleWind / kitesurf tools."""

_SPOT = {
    "type": "string",
    "description": (
        "Kitesurf spot name or numeric ID. Defaults to Oostvoorne (9983) when omitted. "
        "Use wind_search_spots(query='...') to look up other spots."
    ),
}

WIND_CHECK_SPOT_SCHEMA = {
    "name": "wind_check_spot",
    "description": (
        "Check current kitesurf conditions at a Dutch wind spot via actuelewind.nl. "
        "Returns wind speed/gusts/direction, water temperature, waves, sunrise/sunset, "
        "tide times, weather summary, and a kitesurf session verdict. "
        "IDEAL FOR CRON JOBS: call this periodically to monitor whether Oostvoorne "
        "(or another spot) has rideable wind. Defaults to Oostvoorne when spot is omitted."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "spot": _SPOT,
            "forecast_hours": {
                "type": "integer",
                "description": "Hours of hourly forecast to include (default: 12).",
                "default": 12,
            },
            "forecast_days": {
                "type": "integer",
                "description": "Days of forecast data to fetch from the API (default: 1, max 7).",
                "default": 1,
            },
        },
        "required": [],
    },
}

WIND_GET_FORECAST_SCHEMA = {
    "name": "wind_get_forecast",
    "description": (
        "Get hourly wind and weather forecast for a kitesurf spot. "
        "Use after wind_check_spot when the user wants a multi-day outlook. "
        "Defaults to Oostvoorne."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "spot": _SPOT,
            "days": {
                "type": "integer",
                "description": "Forecast days to return (default: 2, max 7).",
                "default": 2,
            },
        },
        "required": [],
    },
}

WIND_SEARCH_SPOTS_SCHEMA = {
    "name": "wind_search_spots",
    "description": (
        "Find a kitesurf spot by name on actuelewind.nl. "
        "Use when the user mentions a spot other than Oostvoorne, or when you need the spot ID."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Spot name or partial name (e.g. 'Oostvoorne', 'Scheveningen').",
            },
            "limit": {
                "type": "integer",
                "description": "Max results for fuzzy search (default: 10).",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}

WIND_LIST_SPOTS_SCHEMA = {
    "name": "wind_list_spots",
    "description": (
        "List available kitesurf spots from actuelewind.nl. "
        "Optionally filter by name substring. Returns spot IDs and coordinates."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional case-insensitive filter on spot name.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum spots to return (default: 20).",
                "default": 20,
            },
        },
        "required": [],
    },
}