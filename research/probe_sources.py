"""Проверка доступности источников данных для проекта «Цены на плодоовощную продукцию».

Запуск:  python research/probe_sources.py
Результат: образцы данных в research/samples/*.csv и сводка в консоли.
Зависимости: requests, pandas.
"""
import re
import sys
import time
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from io import StringIO

import pandas as pd
import requests

OUT = Path(__file__).parent / "samples"
OUT.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}
MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь",
          "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
SDMX_NS = "{http://www.SDMX.org/resources/SDMXML/schemas/v1_0/generic}"

RF = ["Российская Федерация", "Российская Федерация без учета новых субъектов (с 01.01.2023)"]
REGIONS = RF + ["Центральный федеральный округ",
                "Город Москва столица Российской Федерации город федерального значения"]


# ---------- ЕМИСС (fedstat.ru): HTML-страница показателя + выгрузка SDMX ----------

def fedstat_download(indicator, wanted):
    """wanted: {id_фильтра: [названия значений]}; фильтры не из wanted выгружаются целиком."""
    sess = requests.Session()
    html = sess.get(f"https://fedstat.ru/indicator/{indicator}", headers=UA, timeout=60).text
    html = re.sub(re.escape(chr(92)) + r"u([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), html)
    blk = html[html.find("filters: {"):]
    layout, blk = blk[blk.find("left_columns"):], blk[:blk.find("left_columns")]
    left = re.findall(r"\d+", re.search(r"left_columns:\s*\[([^\]]*)\]", layout).group(1))
    top = re.findall(r"\d+", re.search(r"top_columns:\s*\[([^\]]*)\]", layout).group(1))
    parts = re.split(r"\n\s{28}(\d+):\s*\{\s*\n\s*title:\s*'([^']*)'", blk)
    filters = {parts[k]: re.findall(r"'?(\d+)'?:\s*\{\s*title:\s*'([^']*)'", parts[k + 2])
               for k in range(1, len(parts), 3)}
    sel = [f"{fid}_{vid}" for fid, vals in filters.items() for vid, title in vals
           if fid not in wanted or title.strip() in wanted[fid]]
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)
    data = [("id", str(indicator)), ("title", "x"), ("struts.token.name", "token"), ("token", token)]
    data += [("lineObjectIds", f) for f in filters if f not in left + top]
    data += [("lineObjectIds", f) for f in left] + [("columnObjectIds", f) for f in top]
    data += [("selectedFilterIds", s) for s in sel]
    r = sess.post("https://fedstat.ru/indicator/downloadData.do?format=sdmx",
                  data=data, headers=UA, timeout=300)
    r.raise_for_status()
    return parse_sdmx(r.content)


def parse_sdmx(content):
    root = ET.fromstring(content)
    codes = {}
    for cl in root.iter():
        if cl.tag.endswith("CodeList"):
            for c in cl:
                if c.tag.endswith("Code"):
                    d = [x.text for x in c if x.tag.endswith("Description")]
                    codes[(cl.get("id"), c.get("value"))] = d[0] if d else None
    rows = []
    for s in root.iter(SDMX_NS + "Series"):
        key = {v.get("concept"): v.get("value") for v in s.find(SDMX_NS + "SeriesKey")}
        attrs = {v.get("concept"): v.get("value") for v in (s.find(SDMX_NS + "Attributes") or [])}
        for o in s.findall(SDMX_NS + "Obs"):
            rows.append({**key, **attrs, "year": o.find(SDMX_NS + "Time").text,
                         "value": o.find(SDMX_NS + "ObsValue").get("value")})
    df = pd.DataFrame(rows)
    for col in list(df.columns):
        if col.startswith("s_"):
            df[col + "_name"] = [codes.get((col, v)) for v in df[col]]
    df = df[df["PERIOD"].isin(MONTHS)].copy()           # отбрасываем накопленные периоды «январь-март» и т.п.
    df["date"] = pd.to_datetime(df["year"] + "-" + (df["PERIOD"].map(MONTHS.index) + 1).astype(str) + "-01")
    df["value"] = df["value"].str.replace(",", ".").str.replace(" ", "").astype(float)
    return df


def summary(df, by):
    return (df.groupby(by).agg(n=("value", "size"), start=("date", "min"), end=("date", "max"))
              .reset_index().to_string(index=False))


def check(name, fn):
    t0 = time.time()
    try:
        info = fn()
        print(f"\n[OK]   {name}  ({time.time() - t0:.1f} c)\n{info}")
    except Exception as e:  # noqa: BLE001 — это проверочный скрипт, нужен любой сбой
        print(f"\n[FAIL] {name}  ({time.time() - t0:.1f} c): {e!r}")


def src_retail():
    goods = ["Картофель, кг", "Капуста белокочанная свежая, кг", "Лук репчатый, кг", "Морковь, кг",
             "Огурцы свежие, кг", "Помидоры свежие, кг", "Яблоки, кг", "Бананы, кг",
             "Чеснок, кг", "Апельсины, кг"]
    df = fedstat_download(31448, {"58273": goods, "57831": REGIONS})
    df.to_csv(OUT / "emiss_31448_retail_prices.csv", index=False, encoding="utf-8")
    return summary(df, ["s_OKATO_name", "s_grtov_name"])


def src_producer():
    goods = ["Картофель", "Лук репчатый", "Морковь столовая", "Капуста всех сортов",
             "Огурцы", "Томаты (помидоры)", "Свекла столовая"]
    df = fedstat_download(57693, {"57939": goods, "57831": RF + ["Центральный федеральный округ"]})
    df.to_csv(OUT / "emiss_57693_producer_prices.csv", index=False, encoding="utf-8")
    return summary(df, ["s_OKATO_name", "s_OKPD2", "s_OKPD2_name"])


# ---------- Банк России: XML API курсов и HTML-таблица ключевой ставки ----------

def src_cbr_fx():
    frames = []
    for code, cur in [("R01235", "USD"), ("R01239", "EUR")]:
        r = requests.get("https://www.cbr.ru/scripts/XML_dynamic.asp", headers=UA, timeout=60,
                         params={"date_req1": "01/01/2000", "date_req2": time.strftime("%d/%m/%Y"),
                                 "VAL_NM_RQ": code})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        frames.append(pd.DataFrame(
            [{"date": rec.get("Date"), "currency": cur,
              "rate": float(rec.find("Value").text.replace(",", ".")) / int(rec.find("Nominal").text)}
             for rec in root.findall("Record")]))
    df = pd.concat(frames)
    df["date"] = pd.to_datetime(df["date"], format="%d.%m.%Y")
    df.to_csv(OUT / "cbr_fx_daily.csv", index=False)
    return df.groupby("currency").date.agg(["count", "min", "max"]).to_string()


def src_cbr_keyrate():
    r = requests.get("https://www.cbr.ru/hd_base/KeyRate/", headers=UA, timeout=60,
                     params={"UniDbQuery.Posted": "True", "UniDbQuery.From": "17.09.2013",
                             "UniDbQuery.To": time.strftime("%d.%m.%Y")})
    r.raise_for_status()
    df = pd.read_html(StringIO(r.text), decimal=",", thousands=" ")[0]
    df.columns = ["date", "key_rate"]
    df["date"] = pd.to_datetime(df["date"], format="%d.%m.%Y")
    df.to_csv(OUT / "cbr_key_rate.csv", index=False)
    return f"{len(df)} записей, {df.date.min():%Y-%m-%d} … {df.date.max():%Y-%m-%d}"


# ---------- Open-Meteo: JSON REST API исторической погоды ----------

AGRO_POINTS = {  # крупные овощеводческие регионы
    "Липецкая обл.": (52.60, 39.60),
    "Брянская обл.": (53.24, 34.37),
    "Волгоградская обл.": (48.71, 44.51),
    "Краснодарский край": (45.04, 38.98),
    "Московская обл.": (55.75, 37.62),
}


def src_weather():
    frames = []
    for name, (lat, lon) in AGRO_POINTS.items():
        r = requests.get("https://archive-api.open-meteo.com/v1/archive", timeout=120, params={
            "latitude": lat, "longitude": lon, "start_date": "2000-01-01",
            "end_date": time.strftime("%Y-%m-%d"), "timezone": "Europe/Moscow",
            "daily": "temperature_2m_mean,precipitation_sum"})
        r.raise_for_status()
        d = pd.DataFrame(r.json()["daily"])
        d["region"] = name
        frames.append(d)
    df = pd.concat(frames)
    df.to_csv(OUT / "openmeteo_daily.csv", index=False)
    return df.groupby("region").agg(n=("time", "size"), start=("time", "min"), end=("time", "max"),
                                    t_null=("temperature_2m_mean", lambda s: s.isna().sum())).to_string()


if __name__ == "__main__":
    print(sys.version.split()[0], "| pandas", pd.__version__)
    check("ЕМИСС 31448 — средние потребительские цены (месяц, регион)", src_retail)
    check("ЕМИСС 57693 — средние цены производителей с/х продукции (месяц)", src_producer)
    check("Банк России — курсы USD/EUR (XML API)", src_cbr_fx)
    check("Банк России — ключевая ставка (HTML)", src_cbr_keyrate)
    check("Open-Meteo — погода в агрорегионах (JSON API)", src_weather)
