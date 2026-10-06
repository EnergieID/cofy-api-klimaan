import asyncio
import datetime as dt
from typing import Literal

import httpx
import polars as pl
from cofy.modules.timeseries import ISODuration, Timeseries, TimeseriesSource, TimeseriesSourceSettings
from isodate import strftime

ELIA_BASE_URL = "https://opendata.elia.be/api/explore/v2.1/catalog/datasets"
# Near-real-time dataset (today up to a week ahead) first, so it wins over the historical one on overlap.
DATASETS = ("ods087", "ods032")
NATIVE_RESOLUTION = dt.timedelta(minutes=15)

SCHEMA = pl.Schema({"timestamp": pl.Datetime(time_zone="UTC"), "value": pl.Float64})


class EliaSolarForecastSourceSettings(TimeseriesSourceSettings):
    type: Literal["elia_solar_forecast"] = "elia_solar_forecast"
    region: str = "Antwerp"


class EliaSolarForecastSource(TimeseriesSource, settings=EliaSolarForecastSourceSettings):
    SUPPORTED_RESOLUTIONS: list[str] = ["PT15M", "PT1H"]

    def __init__(self, region: str = "Antwerp", transport: httpx.AsyncBaseTransport | None = None) -> None:
        """A TimeseriesSource with Elia's most recent solar production forecast, as % of the monitored PV capacity.

        Args:
            region: The Elia region, e.g. "Belgium", "Flanders" or a province like "Antwerp".
            transport: Optional httpx transport, mainly to mock Elia in tests.
        """
        self.region = region
        self._transport = transport

    async def fetch_timeseries(
        self,
        start: dt.datetime,
        end: dt.datetime,
        resolution: ISODuration,
        **kwargs,
    ) -> Timeseries:
        async with httpx.AsyncClient(base_url=ELIA_BASE_URL, timeout=30, transport=self._transport) as client:
            responses = await asyncio.gather(*(self._fetch_dataset(client, d, start, end) for d in DATASETS))

        records = [record for response in responses for record in response]
        return Timeseries(
            frame=self._build_frame(records, resolution),
            metadata={"unit": "%", "region": self.region, "source": "Elia Open Data"},
        )

    async def _fetch_dataset(
        self, client: httpx.AsyncClient, dataset: str, start: dt.datetime, end: dt.datetime
    ) -> list[dict]:
        response = await client.get(
            f"/{dataset}/exports/json",
            params={
                "where": f'region="{self.region}" and datetime>="{start.isoformat()}" and datetime<"{end.isoformat()}"',
                "select": "datetime,mostrecentforecast,monitoredcapacity",
                "order_by": "datetime",
            },
        )
        if response.status_code != 200:
            raise ValueError(f"Failed to fetch {dataset} from Elia Open Data: {response.status_code} - {response.text}")
        return response.json()

    @staticmethod
    def _build_frame(records: list[dict], resolution: ISODuration) -> pl.DataFrame:
        if not records:
            return pl.DataFrame(schema=SCHEMA)

        capacity = pl.col("monitoredcapacity")
        frame = (
            pl.DataFrame(records, schema_overrides={"mostrecentforecast": pl.Float64, "monitoredcapacity": pl.Float64})
            .select(
                timestamp=pl.col("datetime").str.to_datetime(time_zone="UTC"),
                value=pl.when(capacity > 0)
                .then(pl.col("mostrecentforecast").fill_null(0) / capacity * 100)
                .otherwise(0.0),
            )
            .unique("timestamp", keep="first", maintain_order=True)
            .sort("timestamp")
        )

        if resolution != NATIVE_RESOLUTION:
            if strftime(resolution, "P%P") not in EliaSolarForecastSource.SUPPORTED_RESOLUTIONS:
                raise ValueError(f"Resolution {strftime(resolution, 'P%P')} is not supported.")
            assert isinstance(resolution, dt.timedelta)
            frame = frame.group_by_dynamic("timestamp", every=resolution).agg(pl.col("value").mean())

        return frame.cast(SCHEMA)

    @property
    def supported_resolutions(self) -> list[str]:
        return self.SUPPORTED_RESOLUTIONS

    @property
    def max_age(self) -> dt.timedelta:
        # Elia refreshes its most recent forecast every quarter-hour
        return NATIVE_RESOLUTION
