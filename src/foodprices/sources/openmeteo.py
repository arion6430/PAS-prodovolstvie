"""Open-Meteo Historical Weather API (JSON): дневная погода в точках агрорегионов."""
from __future__ import annotations

import datetime as dt
import json
from typing import Iterable

import pandas as pd
import psycopg

from .base import Payload, Request, SchemaChanged, Source


class OpenMeteo(Source):
    name = "openmeteo"
    table = "raw.openmeteo_daily"
    key_cols = ["point_id", "obs_date"]
    URL = "https://archive-api.open-meteo.com/v1/archive"

    def plan(self, conn: psycopg.Connection) -> Iterable[Request]:
        today = dt.date.today()
        for point_id, pt in self.cfg["points"].items():
            last = conn.execute("SELECT max(obs_date::date) FROM raw.openmeteo_daily WHERE point_id = %s",
                                (point_id,)).fetchone()[0]
            # последние дни архива предварительные — перезапрашиваем их с перекрытием
            since = dt.date.fromisoformat(self.cfg["start_date"]) if last is None \
                else last - dt.timedelta(days=self.cfg["overlap_days"])
            yield Request({"point_id": point_id, "lat": pt["lat"], "lon": pt["lon"], "from": since, "to": today})

    def fetch(self, req: Request) -> Payload:
        p = req.params
        resp = self.http.get(self.URL, params={
            "latitude": p["lat"], "longitude": p["lon"], "timezone": "Europe/Moscow",
            "start_date": p["from"].isoformat(), "end_date": p["to"].isoformat(),
            "daily": ",".join(self.cfg["variables"])})
        data = resp.json()
        if "daily" not in data:
            raise SchemaChanged(f"Open-Meteo: нет блока daily в ответе: {str(data)[:200]}")
        data["point_id"] = p["point_id"]  # чтобы сырой файл был самодостаточным
        content = json.dumps(data, ensure_ascii=False).encode()
        # generationtime_ms меняется от запроса к запросу — в хеш не включаем
        fingerprint = json.dumps({k: v for k, v in data.items() if k != "generationtime_ms"},
                                 sort_keys=True).encode()
        return Payload(content, fingerprint, "json", [])

    def parse(self, payload: Payload) -> pd.DataFrame:
        data = json.loads(payload.content)
        daily = data["daily"]
        missing = {"time", *self.cfg["variables"]} - set(daily)
        if missing:
            raise SchemaChanged(f"Open-Meteo: нет переменных {sorted(missing)}")
        df = pd.DataFrame({
            "point_id": data["point_id"],
            "obs_date": daily["time"],
            "temperature_2m_mean": daily["temperature_2m_mean"],
            "precipitation_sum": daily["precipitation_sum"],
        })
        # пустые значения последних дней не пишем: архив ещё не заполнен
        return df.dropna(subset=["temperature_2m_mean", "precipitation_sum"], how="all")
