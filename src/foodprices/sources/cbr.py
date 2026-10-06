"""Банк России: курсы валют (XML API) и ключевая ставка (HTML-таблица)."""
from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from typing import Iterable

import pandas as pd
import psycopg

from .base import Payload, Request, SchemaChanged, Source, require_columns


def _next_date(conn: psycopg.Connection, query: str, args: tuple, start: str) -> dt.date:
    last = conn.execute(query, args).fetchone()[0]
    return dt.date.fromisoformat(start) if last is None else last + dt.timedelta(days=1)


class CbrFx(Source):
    name = "cbr_fx"
    table = "raw.cbr_fx_rates"
    key_cols = ["currency_id", "rate_date"]
    URL = "https://www.cbr.ru/scripts/XML_dynamic.asp"

    def plan(self, conn: psycopg.Connection) -> Iterable[Request]:
        today = dt.date.today()
        for cur_id, char_code in self.cfg["currencies"].items():
            since = _next_date(conn, "SELECT max(to_date(rate_date, 'DD.MM.YYYY')) FROM raw.cbr_fx_rates "
                                     "WHERE currency_id = %s", (cur_id,), self.cfg["start_date"])
            if since <= today:
                yield Request({"currency_id": cur_id, "char_code": char_code, "from": since, "to": today})

    def fetch(self, req: Request) -> Payload:
        p = req.params
        resp = self.http.get(self.URL, params={"date_req1": p["from"].strftime("%d/%m/%Y"),
                                               "date_req2": p["to"].strftime("%d/%m/%Y"),
                                               "VAL_NM_RQ": p["currency_id"]})
        if b"<ValCurs" not in resp.content[:500]:
            raise SchemaChanged("ЦБ: ответ не похож на ValCurs XML")
        # в ответе есть только данные, без изменчивых полей, — хешируем как есть
        return Payload(resp.content, resp.content, "xml", [])

    def parse(self, payload: Payload) -> pd.DataFrame:
        root = ET.fromstring(payload.content)
        rows = [{"currency_id": r.get("Id"), "rate_date": r.get("Date"),
                 "nominal": r.findtext("Nominal"), "value": r.findtext("Value")}
                for r in root.findall("Record")]
        df = pd.DataFrame(rows, columns=["currency_id", "rate_date", "nominal", "value"])
        df.insert(1, "char_code", df["currency_id"].map(self.cfg["currencies"]))
        return df


class CbrKeyRate(Source):
    name = "cbr_key_rate"
    table = "raw.cbr_key_rate"
    key_cols = ["rate_date"]
    URL = "https://www.cbr.ru/hd_base/KeyRate/"
    ROW = re.compile(r"<tr>\s*<td>(\d{2}\.\d{2}\.\d{4})</td>\s*<td>([^<]*)</td>\s*</tr>")

    def plan(self, conn: psycopg.Connection) -> Iterable[Request]:
        today = dt.date.today()
        since = _next_date(conn, "SELECT max(to_date(rate_date, 'DD.MM.YYYY')) FROM raw.cbr_key_rate", (),
                           self.cfg["start_date"])
        if since <= today:
            yield Request({"from": since, "to": today})

    def fetch(self, req: Request) -> Payload:
        p = req.params
        resp = self.http.get(self.URL, params={"UniDbQuery.Posted": "True",
                                               "UniDbQuery.From": p["from"].strftime("%d.%m.%Y"),
                                               "UniDbQuery.To": p["to"].strftime("%d.%m.%Y")})
        html = resp.text
        if 'class="data"' not in html and "Нет данных" not in html and "не найдены" not in html:
            raise SchemaChanged("ЦБ: на странице ключевой ставки не найдена таблица data")
        # страница содержит меняющиеся элементы (меню, токены), поэтому хешируем только строки таблицы
        rows = self.ROW.findall(html)
        fingerprint = "\n".join(f"{d};{v}" for d, v in rows).encode()
        return Payload(resp.content, fingerprint, "html", [])

    def parse(self, payload: Payload) -> pd.DataFrame:
        rows = self.ROW.findall(payload.content.decode("utf-8", errors="replace"))
        df = pd.DataFrame(rows, columns=["rate_date", "rate"])
        df["rate"] = df["rate"].str.strip()
        require_columns(df, self.key_cols, self.name)
        return df
