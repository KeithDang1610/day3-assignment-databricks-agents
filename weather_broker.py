"""
Open-Meteo weather engine backing the weather-forecast MCP server.

Mirrors the role of alpaca_broker.py in the trading reference repo: this
module is a thin wrapper around a real, hosted weather API
(https://open-meteo.com/). All HTTP calls and JSON parsing live here -
weather_mcp_server.py never calls `requests` directly, it only imports
this module.

Open-Meteo's free, non-commercial tier requires no signup and no API
key, so there is no _secret()/WorkspaceClient().secrets.get_secret()
step here (unlike alpaca_broker.py, which needs Alpaca API keys). If you
swap in a key-based API later (e.g. WeatherAPI.com), add a `_secret()`
helper here following the exact same pattern as alpaca_broker.py - never
hardcode the key.
"""

import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_REQUEST_TIMEOUT = 10  # seconds


def geocode_location(location: str) -> dict:
    """
    Resolve a free-text location name to lat/lon coordinates.

    Args:
        location: City name or similar free text, e.g. "Chicago" or
            "Austin, TX".

    Returns:
        A dict with lat, lon, name, country.

    Raises:
        ValueError: if the location cannot be resolved to any result.
        requests.RequestException: on network/API failure.
    """
    resp = requests.get(
        GEOCODING_URL,
        params={"name": location, "count": 1},
        timeout=_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    results = data.get("results")
    if not results:
        raise ValueError(f"Could not resolve location: {location!r}")

    top = results[0]
    return {
        "lat": top["latitude"],
        "lon": top["longitude"],
        "name": top.get("name", location),
        "country": top.get("country"),
    }


def fetch_current_conditions(lat: float, lon: float) -> dict:
    """
    Fetch current weather conditions for a coordinate pair.

    Args:
        lat: Latitude.
        lon: Longitude.

    Returns:
        A dict with temperature_c, humidity_pct, wind_kph, conditions_code,
        as_of (ISO timestamp).

    Raises:
        requests.RequestException: on network/API failure.
        KeyError: if the API response is missing expected fields.
    """
    resp = requests.get(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            "timezone": "auto",
        },
        timeout=_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    current = resp.json()["current"]

    return {
        "temperature_c": current["temperature_2m"],
        "humidity_pct": current["relative_humidity_2m"],
        "wind_kph": current["wind_speed_10m"],
        "conditions_code": current["weather_code"],
        "as_of": current["time"],
    }


def fetch_daily_forecast(lat: float, lon: float, days: int) -> list[dict]:
    """
    Fetch a multi-day forecast for a coordinate pair.

    Args:
        lat: Latitude.
        lon: Longitude.
        days: Number of days to forecast (1-16, Open-Meteo's supported range).

    Returns:
        A list of dicts, one per day, each with date, temp_high_c,
        temp_low_c, precipitation_probability_pct, conditions_code.

    Raises:
        requests.RequestException: on network/API failure.
        KeyError: if the API response is missing expected fields.
    """
    days = max(1, min(days, 16))

    resp = requests.get(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "forecast_days": days,
            "timezone": "auto",
        },
        timeout=_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    daily = resp.json()["daily"]

    out = []
    for i, date in enumerate(daily["time"]):
        out.append(
            {
                "date": date,
                "temp_high_c": daily["temperature_2m_max"][i],
                "temp_low_c": daily["temperature_2m_min"][i],
                "precipitation_probability_pct": daily["precipitation_probability_max"][i],
                "conditions_code": daily["weather_code"][i],
            }
        )
    return out
