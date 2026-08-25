import os
import logging

import requests
from fastmcp import FastMCP

import weather_broker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather-mcp-server")

mcp = FastMCP("weather-forecast")

# Threshold used by predict_umbrella_needed: if the forecasted chance of
# precipitation is at or above this percentage, we recommend an umbrella.
# This is the "derived judgment call" the assignment asks for - it is not
# a passthrough of the raw API response.
UMBRELLA_PRECIP_THRESHOLD_PCT = 40


def _resolve_location(location: str) -> dict:
    """
    Shared helper: turn a free-text location into coordinates, raising a
    clean ValueError (caught by every tool below) instead of letting a
    stack trace reach the agent.
    """
    return weather_broker.geocode_location(location)


@mcp.tool
def get_current_weather(location: str) -> dict:
    """
    Get current weather conditions for a location.

    Args:
        location: City name or similar free text, e.g. "Chicago" or
            "Austin, TX".

    Returns:
        A dict with location, temperature_c, humidity_pct, wind_kph,
        conditions_code, as_of; or {"error": ...} if the location can't
        be resolved or the API call fails.
    """
    try:
        coords = _resolve_location(location)
        conditions = weather_broker.fetch_current_conditions(coords["lat"], coords["lon"])
        return {
            "location": coords["name"],
            "country": coords["country"],
            **conditions,
        }
    except ValueError as e:
        return {"error": str(e)}
    except requests.RequestException as e:
        logger.exception(f"Weather API call failed for {location!r}")
        return {"error": f"Weather service is unavailable right now: {e}"}


@mcp.tool
def get_forecast(location: str, days: int = 3) -> dict:
    """
    Get a multi-day weather forecast for a location.

    Args:
        location: City name or similar free text, e.g. "Chicago".
        days: Number of days to forecast, 1-16 (default 3).

    Returns:
        A dict with location and a "forecast" list of per-day dicts
        (date, temp_high_c, temp_low_c, precipitation_probability_pct,
        conditions_code); or {"error": ...} on failure.
    """
    try:
        coords = _resolve_location(location)
        forecast = weather_broker.fetch_daily_forecast(coords["lat"], coords["lon"], days)
        return {
            "location": coords["name"],
            "country": coords["country"],
            "forecast": forecast,
        }
    except ValueError as e:
        return {"error": str(e)}
    except requests.RequestException as e:
        logger.exception(f"Weather API call failed for {location!r}")
        return {"error": f"Weather service is unavailable right now: {e}"}


@mcp.tool
def predict_umbrella_needed(location: str, date: str) -> dict:
    """
    Recommend whether to bring an umbrella on a given date, based on the
    forecasted chance of precipitation.

    Decision rule: if precipitation_probability_pct for that date is >=
    UMBRELLA_PRECIP_THRESHOLD_PCT (currently 40%), recommend an umbrella.
    This is a threshold-based judgment call on top of the raw forecast,
    not just an echo of the API response.

    Args:
        location: City name or similar free text, e.g. "Chicago".
        date: Target date in YYYY-MM-DD format. Must fall within the next
            16 days (Open-Meteo's forecast range).

    Returns:
        A dict with location, date, precipitation_probability_pct,
        umbrella_recommended (bool), and reason; or {"error": ...} if the
        location/date can't be resolved or the API call fails.
    """
    try:
        coords = _resolve_location(location)
        # Fetch enough days to cover the requested date, then find it.
        forecast = weather_broker.fetch_daily_forecast(coords["lat"], coords["lon"], days=16)
        day = next((d for d in forecast if d["date"] == date), None)

        if day is None:
            return {
                "error": (
                    f"No forecast available for {date!r} in {coords['name']}. "
                    "Forecasts are only available for the next 16 days."
                )
            }

        precip_pct = day["precipitation_probability_pct"]
        needs_umbrella = precip_pct >= UMBRELLA_PRECIP_THRESHOLD_PCT

        return {
            "location": coords["name"],
            "date": date,
            "precipitation_probability_pct": precip_pct,
            "umbrella_recommended": needs_umbrella,
            "reason": (
                f"Precipitation probability is {precip_pct}%, which is "
                f"{'at or above' if needs_umbrella else 'below'} the "
                f"{UMBRELLA_PRECIP_THRESHOLD_PCT}% threshold."
            ),
        }
    except ValueError as e:
        return {"error": str(e)}
    except requests.RequestException as e:
        logger.exception(f"Weather API call failed for {location!r}")
        return {"error": f"Weather service is unavailable right now: {e}"}


if __name__ == "__main__":
    # Databricks Apps route external HTTP traffic to this port via app.yaml;
    # streamable-http is the transport Databricks' MCP client/gateway expects.
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", 8000)))
    mcp.run(transport="http", host="0.0.0.0", port=port)
