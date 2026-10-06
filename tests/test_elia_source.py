import datetime as dt
import json

import httpx
import polars as pl
import pytest
from cofy.modules.directive import DirectiveSource
from cofy.modules.timeseries import ISODuration, Timeseries, TimeseriesSource

from solar import EliaSolarForecastSource

QUARTER_HOUR = dt.timedelta(minutes=15)


def record(timestamp: str, forecast: float | None, capacity: float | None = 1000.0) -> dict:
    return {"datetime": timestamp, "mostrecentforecast": forecast, "monitoredcapacity": capacity}


def test_build_frame_computes_share_of_capacity():
    frame = EliaSolarForecastSource._build_frame(
        [
            record("2026-06-21T10:00:00+00:00", 600.0),
            record("2026-06-21T10:15:00+00:00", None),
            record("2026-06-21T10:30:00+00:00", 100.0, capacity=0.0),
            record("2026-06-21T10:45:00+00:00", 100.0, capacity=None),
        ],
        QUARTER_HOUR,
    )

    assert frame["value"].to_list() == [60.0, 0.0, 0.0, 0.0]
    assert frame["timestamp"][0] == dt.datetime(2026, 6, 21, 10, tzinfo=dt.UTC)


def test_build_frame_aggregates_to_hours():
    records = [
        record(f"2026-06-21T10:{m:02d}:00+00:00", v) for m, v in zip((0, 15, 30, 45), (100, 200, 300, 400), strict=True)
    ]
    records.append(record("2026-06-21T11:00:00+00:00", 500))

    frame = EliaSolarForecastSource._build_frame(records, dt.timedelta(hours=1))

    assert frame["value"].to_list() == [25.0, 50.0]


def test_build_frame_empty():
    frame = EliaSolarForecastSource._build_frame([], QUARTER_HOUR)

    assert frame.is_empty()
    assert frame.schema == pl.Schema({"timestamp": pl.Datetime(time_zone="UTC"), "value": pl.Float64})


def test_build_frame_rejects_unsupported_resolution():
    with pytest.raises(ValueError, match="not supported"):
        EliaSolarForecastSource._build_frame([record("2026-06-21T10:00:00+00:00", 1.0)], dt.timedelta(days=1))


async def test_fetch_merges_datasets_preferring_near_real_time():
    responses = {
        "ods087": [record("2026-06-21T10:15:00+00:00", 500.0), record("2026-06-21T10:30:00+00:00", 600.0)],
        "ods032": [record("2026-06-21T10:00:00+00:00", 400.0), record("2026-06-21T10:15:00+00:00", 1.0)],
    }
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        dataset = request.url.path.split("/")[-3]
        return httpx.Response(200, content=json.dumps(responses[dataset]))

    source = EliaSolarForecastSource(region="Antwerp", transport=httpx.MockTransport(handler))
    start = dt.datetime(2026, 6, 21, 10, tzinfo=dt.UTC)
    timeseries = await source.fetch_timeseries(start, start + dt.timedelta(hours=1), QUARTER_HOUR)

    assert timeseries.frame["value"].to_list() == [40.0, 50.0, 60.0]
    assert timeseries.metadata["unit"] == "%"
    assert all('region="Antwerp"' in r.url.params["where"] for r in requests)


async def test_fetch_raises_on_error():
    source = EliaSolarForecastSource(transport=httpx.MockTransport(lambda _: httpx.Response(500, text="boom")))
    start = dt.datetime(2026, 6, 21, tzinfo=dt.UTC)

    with pytest.raises(ValueError, match="500"):
        await source.fetch_timeseries(start, start + QUARTER_HOUR, QUARTER_HOUR)


class StubSource(TimeseriesSource):
    def __init__(self, values: list[float]):
        self.values = values

    async def fetch_timeseries(self, start: dt.datetime, end: dt.datetime, resolution: ISODuration, **kwargs):
        timestamps = [start + i * QUARTER_HOUR for i in range(len(self.values))]
        return Timeseries(frame=pl.DataFrame({"timestamp": timestamps, "value": self.values}))


async def test_directive_is_positive_with_high_solar_share():
    source = DirectiveSource(StubSource([0.0, 3.0, 10.0, 30.0, 50.0]), boundaries=(0, 5, 20, 40))
    start = dt.datetime(2026, 6, 21, tzinfo=dt.UTC)

    timeseries = await source.fetch_timeseries(start, start + dt.timedelta(hours=2), QUARTER_HOUR)

    assert timeseries.frame["value"].to_list() == ["--", "-", "0", "+", "++"]


def test_source_can_be_created_from_settings():
    source = TimeseriesSource.create({"type": "elia_solar_forecast", "region": "Flanders"})

    assert isinstance(source, EliaSolarForecastSource)
    assert source.region == "Flanders"
