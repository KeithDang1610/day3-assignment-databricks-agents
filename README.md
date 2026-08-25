# Weather Forecast MCP Server + Agent Bricks Agent

Built as a follow-up to Day 3 (`databricks-lakebase-app-day-3`), reusing the
same MCP server / Databricks App pattern used for the Alpaca Markets
paper-trading MCP server, applied to weather instead of trading.

## Overview

This project exposes weather-forecast tools through an MCP server and wires
a Databricks Agent Bricks agent to use those tools to answer natural-language
weather questions (e.g. "Will it rain in Chicago tomorrow?", "Should I bring
a jacket to Austin this weekend?").

## Architecture

```
┌─────────────────────┐        ┌──────────────────────┐        ┌───────────────────┐
│  Agent Bricks agent  │ ─────▶ │  Weather MCP Server    │ ─────▶ │  Open-Meteo API     │
│  (system prompt +    │  MCP   │  (weather_mcp_server.py)│  HTTP  │  (no key required)  │
│   tool calls)        │ ◀───── │  weather_broker.py      │ ◀───── │                    │
└─────────────────────┘        └──────────────────────┘        └───────────────────┘
```

- **`weather_mcp_server.py`** — FastMCP server exposing `@mcp.tool` functions.
  Tools stay thin: no raw `requests` calls, only calls into the broker module.
- **`weather_broker.py`** — adapter module holding all HTTP calls and JSON
  parsing for the weather API. Mirrors the role of `alpaca_broker.py` in the
  Day 3 reference repo.
- Both files are deployed together as a single Databricks App
  (`mcp_server/`), following the same `requirements.txt` + `app.yaml` pattern
  as Day 3.

## Weather API + auth method

**Open-Meteo** (https://open-meteo.com/) — chosen because it requires zero
credentials (no signup, no API key), which let the whole pipeline be built
and tested before any secrets management was needed. No Databricks secret
scope is used in this project as a result.

Two endpoints are used:
- `https://geocoding-api.open-meteo.com/v1/search` — resolves a free-text
  location name to latitude/longitude.
- `https://api.open-meteo.com/v1/forecast` — returns current conditions and
  daily forecast data for a given coordinate pair.

*(Not implemented in this version, but noted as a natural extension: the
National Weather Service API (`api.weather.gov`) could be layered in as a
second tool for US-specific severe weather alerts. It also requires no API
key, only a `User-Agent` header on every request.)*

## Tools

| Tool | Description |
|---|---|
| `get_current_weather(location)` | Current temperature, humidity, wind, and conditions code for a location. |
| `get_forecast(location, days)` | Multi-day forecast (1–16 days): daily high/low temp, precipitation probability, conditions code. |
| `predict_umbrella_needed(location, date)` | Recommends whether to bring an umbrella on a given date. Applies a threshold rule: umbrella is recommended if the forecasted precipitation probability is ≥ 40%. This is a derived judgment call on top of the raw forecast data, not a passthrough. |

All three tools:
- Resolve `location` via geocoding before calling the forecast API.
- Return a clean `{"error": "..."}` dict (not a stack trace) if the location
  can't be resolved or the API call fails, so the agent can react sensibly
  instead of hallucinating.

## Project structure

```
mcp_server/
├── weather_mcp_server.py   # @mcp.tool definitions (thin)
├── weather_broker.py        # all HTTP calls + JSON parsing
├── requirements.txt
└── app.yaml
README.md
```

## Setup / Deployment steps

1. **Install dependencies locally (optional, for testing before deploy):**
   ```bash
   pip install -r mcp_server/requirements.txt
   ```

2. **Run the MCP server locally:**
   ```bash
   cd mcp_server
   python weather_mcp_server.py
   ```
   The server listens on `0.0.0.0:8000` by default (configurable via the
   `DATABRICKS_APP_PORT` or `PORT` environment variable).

3. **Smoke-test the tools** using an MCP inspector or a small test script
   against `get_current_weather`, `get_forecast`, and
   `predict_umbrella_needed` before deploying.

4. **Deploy as a Databricks App:**
   - Push the `mcp_server/` folder to the Databricks workspace / repo.
   - Databricks reads `app.yaml` (`command: ["python", "weather_mcp_server.py"]`)
     to start the app, and `requirements.txt` to install dependencies.
   - Confirm the app is reachable at its assigned Databricks App URL.

5. **Register the MCP server as an external MCP** in Agent Bricks (same
   steps as Day 3's README, section "Register the MCP server as an external
   MCP").

6. **Build the Agent Bricks agent** and attach the registered MCP server as
   a tool. Use the system prompt below.

## Agent system prompt

```
You are a weather assistant. You have access to three tools:
get_current_weather, get_forecast, and predict_umbrella_needed.

Rules:
1. Always call the appropriate tool to answer weather questions. Never
   guess or make up weather data — only report what a tool call returns.
2. To resolve "today", "tomorrow", or "this weekend" into a specific date,
   compute it from the current date and pass an explicit YYYY-MM-DD date
   to predict_umbrella_needed.
3. If a tool call returns an "error" field, tell the user the specific
   problem (e.g. location not found, service unavailable) and ask them to
   clarify or try again — do not fabricate a weather answer.
4. If a user asks about a location outside the next 16 days' forecast
   range, tell them forecasts aren't available that far out.
5. Keep answers concise and directly address what the user asked
   (temperature, rain chance, whether to bring an umbrella/jacket, etc.).
```

## Error handling

- Unresolvable locations raise a `ValueError` in the broker, caught by
  every tool and returned as `{"error": "Could not resolve location: ..."}`.
- Network/API failures raise `requests.RequestException`, caught and
  returned as `{"error": "Weather service is unavailable right now: ..."}`.
- No secrets are committed to the repo (Open-Meteo requires none).

## Demo

*(Paste or screenshot at least 3 natural-language questions and the agent's
tool-calling + final answers here after deployment.)*

1. **Q:** "Will it rain in Chicago tomorrow?"
   **Tool call:** `predict_umbrella_needed(location="Chicago", date="...")`
   **A:** _...(paste agent response)..._

2. **Q:** "Should I bring a jacket to Austin this weekend?"
   **Tool call:** `get_forecast(location="Austin", days=...)`
   **A:** _...(paste agent response)..._

3. **Q:** "What's the weather in [invalid location]?"
   **Tool call:** `get_current_weather(location="...")` → returns `error`
   **A:** _...(paste agent response showing graceful error handling)..._
