"""
Cofy API - application entrypoint.

This file bootstraps the CofyApi app and registers the modules you need.
See https://github.com/EnergieID/cofy-api for all available modules & options.

Quick start:
  1. Copy .env.example → .env and fill in your values
  2. `uv sync` to install dependencies
  3. `poe dev` to start the dev server (auto-reloads, reads .env)
"""

import datetime as dt
from os import environ

from cofy.api import CofyAPI, TokenAuth, TokenInfo
from cofy.modules.directive import DirectiveModule, DirectiveSource
from cofy.modules.timeseries import CachedTimeseriesSource, floor_datetime

from solar import EliaSolarForecastSource

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
# TokenAuth protects all module endpoints with a simple bearer token.
cofy = CofyAPI(auth=TokenAuth({environ.get("ENERGY_ID_COFY_API_TOKEN", ""): TokenInfo(name="EnergyID")}))

# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------
# --- Solar directive --------------------------------------------------------
# Elia's solar production forecast for the Antwerp province,
# as % of the monitored PV capacity, mapped to directive steps
QUARTER_HOUR = dt.timedelta(minutes=15)


def _now() -> dt.datetime:
    return floor_datetime(dt.datetime.now(dt.UTC), QUARTER_HOUR)


cofy.register_module(
    DirectiveModule(
        source=DirectiveSource(
            CachedTimeseriesSource(EliaSolarForecastSource(region="Antwerp")),
            boundaries=(0, 3, 12, 40),
        ),
        name="solar",
        description="Directive based on Elia's solar production forecast for the Antwerp province",
        default_args={
            "resolution": "PT15M",
            # forward-looking by default: the next 24 hours
            "start": _now,
            "end": lambda: _now() + dt.timedelta(days=1),
        },
    )
)
