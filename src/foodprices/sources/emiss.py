"""ЕМИСС (fedstat.ru): выгрузка показателя в SDMX-XML.

Официального API нет, поэтому повторяем то, что делает сама страница показателя:
1) GET /indicator/<id> — в HTML-коде есть описание фильтров (измерений) с id значений и токен формы;
2) POST /indicator/downloadData.do?format=sdmx — с выбранными значениями фильтров.
"""
from __future__ import annotations

import csv
import datetime as dt
import logging
import re
import xml.etree.ElementTree as ET
from typing import Iterable

import pandas as pd
import psycopg

from ..settings import PROJECT_ROOT
from .base import Payload, Request, SchemaChanged, Source, require_columns

log = logging.getLogger(__name__)

BASE = "https://fedstat.ru"
GENERIC = "{http://www.SDMX.org/resources/SDMXML/schemas/v1_0/generic}"
SEEDS = PROJECT_ROOT / "dbt" / "seeds"


class FedstatIndicator:
    """Описание показателя со страницы ЕМИСС: фильтры, раскладка таблицы, токен формы."""

    def __init__(self, html: str):
        html = re.sub(re.escape(chr(92)) + r"u([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), html)
        start = html.find("filters: {")
        if start < 0:
            raise SchemaChanged("ЕМИСС: на странице показателя не найден блок filters")
        block = html[start:]
        layout = block[block.find("left_columns"):]
        block = block[:block.find("left_columns")]
        try:
            self.left = re.findall(r"\d+", re.search(r"left_columns:\s*\[([^\]]*)\]", layout).group(1))
            self.top = re.findall(r"\d+", re.search(r"top_columns:\s*\[([^\]]*)\]", layout).group(1))
            self.token = re.search(r'name="token" value="([^"]+)"', html).group(1)
        except AttributeError as e:
            raise SchemaChanged("ЕМИСС: не удалось разобрать раскладку таблицы или токен") from e
        # заголовок фильтра отличается от значения тем, что до «values: {» нет фигурных скобок
        parts = re.split(r"\n\s*(\d+):\s*\{\s*\n\s*title:\s*'([^']*)',(?=[^{}]*values:\s*\{)", block)
        # filters: id фильтра -> (название, [(id значения, название значения)])
        self.filters: dict[str, tuple[str, list[tuple[str, str]]]] = {}
        for k in range(1, len(parts), 3):
            values = re.findall(r"'?(\d+)'?:\s*\{\s*title:\s*'([^']*)'", parts[k + 2])
            self.filters[parts[k]] = (parts[k + 1], [(v, t.strip()) for v, t in values])

    def find_filter(self, title_prefix: str) -> str:
        for fid, (title, _) in self.filters.items():
            if title.startswith(title_prefix):
                return fid
        raise SchemaChanged(f"ЕМИСС: нет фильтра «{title_prefix}…»; есть {[t for t, _ in self.filters.values()]}")

    def form(self, indicator_id: int, selected: dict[str, set[str]]) -> tuple[list[tuple[str, str]], list[str]]:
        """Тело POST-запроса. selected: id фильтра -> названия значений; прочие фильтры берутся целиком.
        Возвращает (форма, предупреждения о значениях, которых в источнике больше нет)."""
        warnings = []
        sel = []
        for fid, (ftitle, values) in self.filters.items():
            want = selected.get(fid)
            if want is not None:
                missing = want - {t for _, t in values}
                warnings += [f"ЕМИСС {indicator_id}: в фильтре «{ftitle}» нет значения «{m}»" for m in sorted(missing)]
            sel += [f"{fid}_{vid}" for vid, title in values if want is None or title in want]
        data = [("id", str(indicator_id)), ("title", "foodprices"),
                ("struts.token.name", "token"), ("token", self.token)]
        data += [("lineObjectIds", f) for f in self.filters if f not in self.left + self.top]
        data += [("lineObjectIds", f) for f in self.left] + [("columnObjectIds", f) for f in self.top]
        data += [("selectedFilterIds", s) for s in sel]
        return data, warnings


def parse_sdmx(content: bytes) -> pd.DataFrame:
    """SDMX 1.0 Generic → таблица: измерения серии + атрибуты + время + значение, плюс названия кодов."""
    root = ET.fromstring(content)
    codes: dict[tuple[str, str], str] = {}
    for cl in root.iter():
        if cl.tag.endswith("CodeList"):
            for c in cl:
                if c.tag.endswith("Code"):
                    desc = next((d.text for d in c if d.tag.endswith("Description")), None)
                    codes[(cl.get("id"), c.get("value"))] = desc
    rows = []
    for s in root.iter(GENERIC + "Series"):
        key = {v.get("concept"): v.get("value") for v in s.find(GENERIC + "SeriesKey")}
        attrs_el = s.find(GENERIC + "Attributes")
        attrs = {v.get("concept"): v.get("value") for v in attrs_el} if attrs_el is not None else {}
        for o in s.findall(GENERIC + "Obs"):
            rows.append({**key, **attrs, "TIME": o.find(GENERIC + "Time").text,
                         "VALUE": o.find(GENERIC + "ObsValue").get("value")})
    df = pd.DataFrame(rows)
    for col in [c for c in df.columns if c.startswith("s_")]:
        df[col + "_name"] = [codes.get((col, v)) for v in df[col]]
    return df


def strip_header(content: bytes) -> bytes:
    """Заголовок SDMX содержит ID и время формирования — для хеша его убираем."""
    return re.sub(rb"<Header.*?</Header>", b"", content, count=1, flags=re.S)


def read_seed(name: str) -> list[dict[str, str]]:
    with open(SEEDS / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


class EmissSource(Source):
    seed_source: str           # значение колонки source в product_mapping.csv
    product_filter: str        # начало названия фильтра с товарами
    region_filter = "Классификатор объектов административно-территориального деления"
    chunk_years = 6            # лет в одном запросе — ответы не слишком большие, сбой затрагивает часть окна

    def _years(self, conn: psycopg.Connection) -> list[int]:
        last = conn.execute(f"SELECT max(year) FROM {self.table}").fetchone()[0]
        start = self.cfg["start_year"] if last is None else max(self.cfg["start_year"],
                                                                 last - self.cfg["reload_years"] + 1)
        return list(range(start, dt.date.today().year + 1))

    def plan(self, conn: psycopg.Connection) -> Iterable[Request]:
        years = self._years(conn)
        products = {r["source_name"] for r in read_seed("product_mapping.csv") if r["source"] == self.seed_source}
        regions = {r["source_name"] for r in read_seed("region_mapping.csv")}
        for i in range(0, len(years), self.chunk_years):
            yield Request({"indicator_id": self.cfg["indicator_id"], "years": years[i:i + self.chunk_years],
                           "products": sorted(products), "regions": sorted(regions)})

    def fetch(self, req: Request) -> Payload:
        p = req.params
        page = self.http.get(f"{BASE}/indicator/{p['indicator_id']}")
        ind = FedstatIndicator(page.text)
        selected = {
            ind.find_filter("Год"): {str(y) for y in p["years"]},
            ind.find_filter(self.product_filter): set(p["products"]),
            ind.find_filter(self.region_filter): set(p["regions"]),
        }
        form, warnings = ind.form(p["indicator_id"], selected)
        resp = self.http.post(f"{BASE}/indicator/downloadData.do?format=sdmx", data=form)
        if b"<GenericData" not in resp.content[:2000]:
            raise SchemaChanged(f"ЕМИСС: вместо SDMX пришёл ответ типа {resp.headers.get('content-type')}")
        return Payload(resp.content, strip_header(resp.content), "xml", warnings)


class EmissRetail(EmissSource):
    name = "emiss_retail"
    table = "raw.emiss_retail_prices"
    key_cols = ["okato_code", "good_code", "year", "period_name"]
    seed_source = "emiss_retail"
    product_filter = "Виды товаров и услуг"

    def parse(self, payload: Payload) -> pd.DataFrame:
        df = parse_sdmx(payload.content)
        if df.empty:
            return pd.DataFrame(columns=self.key_cols)
        require_columns(df, ["s_OKATO", "s_grtov", "EI", "PERIOD", "TIME", "VALUE"], self.name)
        return pd.DataFrame({
            "okato_code": df["s_OKATO"], "okato_name": df["s_OKATO_name"],
            "good_code": df["s_grtov"], "good_name": df["s_grtov_name"], "unit": df["EI"],
            "year": df["TIME"].astype(int), "period_name": df["PERIOD"], "value": df["VALUE"],
        })


class EmissProducer(EmissSource):
    name = "emiss_producer"
    table = "raw.emiss_producer_prices"
    key_cols = ["okato_code", "okpd2_code", "okei_code", "year", "period_name"]
    seed_source = "emiss_producer"
    product_filter = "Классификатор продукции по видам экономической деятельности"

    def parse(self, payload: Payload) -> pd.DataFrame:
        df = parse_sdmx(payload.content)
        if df.empty:
            return pd.DataFrame(columns=self.key_cols)
        require_columns(df, ["s_OKATO", "s_OKPD2", "s_OKEI", "PERIOD", "TIME", "VALUE"], self.name)
        return pd.DataFrame({
            "okato_code": df["s_OKATO"], "okato_name": df["s_OKATO_name"],
            "okpd2_code": df["s_OKPD2"], "okpd2_name": df["s_OKPD2_name"],
            "okei_code": df["s_OKEI"], "okei_name": df["s_OKEI_name"],
            "year": df["TIME"].astype(int), "period_name": df["PERIOD"], "value": df["VALUE"],
        })
