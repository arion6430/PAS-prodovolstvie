"""Дашборды как код: создаёт/обновляет в Superset подключение к хранилищу, датасеты, графики и дашборды.

Запускается сервисом superset-bootstrap (docker compose) или вручную:
    docker compose run --rm superset-bootstrap
Идемпотентен: объекты ищутся по имени (подключение), схеме+таблице (датасет), названию (график), slug (дашборд)
и обновляются, а не дублируются. Каждый график назван вопросом пользователя, на который он отвечает.
"""
from __future__ import annotations

import json
import os
import sys
import time

import requests

URL = os.environ.get("SUPERSET_URL", "http://localhost:8088")
ADMIN = os.environ.get("SUPERSET_ADMIN_USER", "admin")
ADMIN_PWD = os.environ.get("SUPERSET_ADMIN_PASSWORD", "admin")
DB_NAME = "Хранилище цен (витрины)"
DB_URI = (f"postgresql+psycopg2://{os.environ.get('BI_READER_USER', 'bi_reader')}:"
          f"{os.environ.get('BI_READER_PASSWORD', '')}@postgres:5432/{os.environ.get('WAREHOUSE_DB', 'foodprices')}")
WAIT_TABLES_SEC = int(os.environ.get("SUPERSET_WAIT_TABLES_SEC", "1800"))

# ---------- подписи колонок (verbose_name) ----------
LABELS = {
    "product_name": "Товар", "category": "Группа товаров", "origin": "Происхождение", "region_name": "Регион",
    "region_short": "Регион (кратко)", "region_level": "Уровень", "period_month": "Месяц", "price_rub_kg": "Цена, руб/кг",
    "price_prev_month": "Цена месяц назад", "mom_pct": "За месяц, %", "price_prev_year": "Цена год назад",
    "yoy_pct": "За год, %", "seasonal_norm_rub_kg": "Сезонная норма, руб/кг",
    "dev_from_norm_pct": "Отклонение от нормы, %", "producer_price_rub_kg": "Цена производителя, руб/кг",
    "retail_to_producer_ratio": "Розница / производитель, раз", "usd_rub": "Курс USD, руб",
    "key_rate_pct": "Ключевая ставка, %", "corr_with_usd": "Корреляция с курсом USD",
    "corr_with_usd_lag3": "Корреляция с курсом USD (лаг 3 мес.)", "n_months": "Месяцев в расчёте",
    "dependence": "Зависимость", "source": "Код источника", "source_title": "Источник", "frequency": "Частота",
    "last_data_date": "Последние данные", "lag_days": "Отставание, дн.", "max_lag_days": "Допустимо, дн.",
    "last_run_msk": "Последний запуск", "last_ok_run_msk": "Последний успешный", "last_status": "Статус запуска",
    "problems_7d": "Сбоев за 7 дней", "freshness_status": "Состояние", "load_id": "ID загрузки",
    "trigger_type": "Запуск", "status": "Статус", "started_msk": "Начало (МСК)", "load_date": "Дата",
    "duration_sec": "Длительность, с", "requests_total": "Запросов", "requests_failed": "Ошибок запросов",
    "rows_received": "Строк получено", "rows_inserted": "Новых строк", "rows_updated": "Изменённых строк",
    "rows_unchanged": "Без изменений", "warnings_count": "Предупреждений", "error": "Ошибка",
    "check_name": "Проверка", "check_type": "Тип проверки", "affected_rows": "Затронуто строк",
    "system_action": "Действие системы",
}

DATASETS = ["mart_price_monthly", "mart_price_latest", "mart_fx_sensitivity",
            "ops_source_freshness", "ops_load_log", "ops_data_quality"]


def metric(sql: str, label: str) -> dict:
    return {"expressionType": "SQL", "sqlExpression": sql, "label": label}


def time_filter(col: str) -> list[dict]:
    return [{"clause": "WHERE", "expressionType": "SIMPLE", "subject": col,
             "operator": "TEMPORAL_RANGE", "comparator": "No filter"}]


# ---------- графики: (ключ, датасет, название-вопрос, тип, параметры) ----------
CHARTS = {
    # --- предметный дашборд ---
    "latest_table": ("mart_price_latest", "Сколько стоит товар сейчас и как изменилась цена?", "table", {
        "query_mode": "raw", "show_cell_bars": False,
        "all_columns": ["product_name", "period_month", "price_rub_kg", "mom_pct", "yoy_pct",
                        "seasonal_norm_rub_kg", "dev_from_norm_pct", "retail_to_producer_ratio"],
        "order_by_cols": [json.dumps(["dev_from_norm_pct", False])],
        "row_limit": 100, "table_timestamp_format": "%m.%Y", "include_search": False,
        "conditional_formatting": [
            {"column": "dev_from_norm_pct", "operator": ">", "targetValue": 20, "colorScheme": "#E04355"},
            {"column": "dev_from_norm_pct", "operator": "<", "targetValue": -10, "colorScheme": "#5AC189"},
        ],
    }),
    "norm_bar": ("mart_price_latest", "Какие товары сейчас дороже сезонной нормы?", "echarts_timeseries_bar", {
        "x_axis": "product_name", "metrics": [metric("MAX(dev_from_norm_pct)", "Отклонение от нормы, %")],
        "groupby": [], "orientation": "horizontal", "x_axis_sort": "Отклонение от нормы, %",
        "x_axis_sort_asc": True, "row_limit": 100, "show_legend": False, "show_value": True,
        "y_axis_format": "SMART_NUMBER",
        "adhoc_filters": [{"clause": "WHERE", "expressionType": "SQL", "sqlExpression": "dev_from_norm_pct IS NOT NULL"}],
    }),
    "price_line": ("mart_price_monthly", "Как менялись цены?", "echarts_timeseries_line", {
        "x_axis": "period_month", "time_grain_sqla": "P1M",
        "metrics": [metric("AVG(price_rub_kg)", "Цена, руб/кг")], "groupby": ["product_name"],
        "adhoc_filters": time_filter("period_month"), "row_limit": 50000, "show_legend": True,
        "rich_tooltip": True, "y_axis_title": "руб/кг", "y_axis_title_position": "Left",
    }),
    "norm_line": ("mart_price_monthly", "Цена против сезонной нормы: аномалия или обычная сезонность?",
                  "echarts_timeseries_line", {
        "x_axis": "period_month", "time_grain_sqla": "P1M",
        "metrics": [metric("AVG(price_rub_kg)", "Цена, руб/кг"),
                    metric("AVG(seasonal_norm_rub_kg)", "Сезонная норма, руб/кг")],
        "groupby": [], "adhoc_filters": time_filter("period_month"), "row_limit": 50000,
        "show_legend": True, "rich_tooltip": True, "y_axis_title": "руб/кг", "y_axis_title_position": "Left",
    }),
    "markup_line": ("mart_price_monthly", "Во сколько раз розничная цена выше цены производителя?",
                    "echarts_timeseries_line", {
        "x_axis": "period_month", "time_grain_sqla": "P1M",
        "metrics": [metric("AVG(retail_to_producer_ratio)", "Розница / производитель, раз")],
        "groupby": ["product_name"], "adhoc_filters": time_filter("period_month"), "row_limit": 50000,
        "show_legend": True, "rich_tooltip": True,
    }),
    "region_heatmap": ("mart_price_latest", "В каких регионах цены сильнее всего выше нормы?", "heatmap_v2", {
        "x_axis": "region_short", "groupby": "product_name",
        "metric": metric("MAX(dev_from_norm_pct)", "Отклонение от нормы, %"),
        "linear_color_scheme": "superset_seq_1", "show_values": True, "show_legend": True,
        "normalize_across": "heatmap", "row_limit": 1000, "sort_x_axis": "alpha_asc", "sort_y_axis": "alpha_asc",
        "value_bounds": [None, None], "y_axis_format": "SMART_NUMBER", "xscale_interval": 1, "yscale_interval": 1,
        "adhoc_filters": [{"clause": "WHERE", "expressionType": "SQL", "sqlExpression": "dev_from_norm_pct IS NOT NULL"}],
    }),
    "fx_bar": ("mart_fx_sensitivity", "Какие товары подорожают, если ослабнет рубль?", "echarts_timeseries_bar", {
        "x_axis": "product_name",
        "metrics": [metric("MAX(corr_with_usd)", "Сразу"), metric("MAX(corr_with_usd_lag3)", "Через 3 месяца")],
        "groupby": [], "orientation": "horizontal", "x_axis_sort": "Через 3 месяца", "x_axis_sort_asc": True,
        "row_limit": 100, "show_legend": True, "show_value": False,
        "adhoc_filters": [{"clause": "WHERE", "expressionType": "SQL", "sqlExpression": "n_months >= 36"}],
    }),
    # --- операционный дашборд ---
    "freshness_table": ("ops_source_freshness", "Актуальны ли данные всех источников?", "table", {
        "query_mode": "raw", "show_cell_bars": False,
        "all_columns": ["source_title", "freshness_status", "last_data_date", "lag_days", "max_lag_days",
                        "last_ok_run_msk", "last_status", "problems_7d"],
        "order_by_cols": [], "row_limit": 100, "table_timestamp_format": "%d.%m.%Y %H:%M",
        "conditional_formatting": [
            {"column": "problems_7d", "operator": ">", "targetValue": 0, "colorScheme": "#E04355"},
        ],
    }),
    "loads_by_status": ("ops_load_log", "Стабильно ли проходят загрузки?", "echarts_timeseries_bar", {
        "x_axis": "load_date", "time_grain_sqla": "P1D", "metrics": [metric("COUNT(*)", "Загрузок")],
        "groupby": ["status"], "stack": "Stack", "adhoc_filters": time_filter("load_date"),
        "row_limit": 10000, "show_legend": True, "rich_tooltip": True,
    }),
    "rows_by_day": ("ops_load_log", "Сколько новых данных и ревизий приходит?", "echarts_timeseries_bar", {
        "x_axis": "load_date", "time_grain_sqla": "P1D",
        "metrics": [metric("SUM(rows_inserted)", "Новых строк"), metric("SUM(rows_updated)", "Изменённых строк")],
        "groupby": [], "adhoc_filters": time_filter("load_date"), "row_limit": 10000,
        "show_legend": True, "rich_tooltip": True, "logAxis": True,
    }),
    "loads_table": ("ops_load_log", "Что произошло в последних запусках?", "table", {
        "query_mode": "raw", "show_cell_bars": False,
        "all_columns": ["started_msk", "source_title", "status", "trigger_type", "duration_sec",
                        "requests_failed", "rows_inserted", "rows_updated", "rows_unchanged",
                        "warnings_count", "error"],
        "order_by_cols": [json.dumps(["load_id", False])], "row_limit": 50,
        "table_timestamp_format": "%d.%m.%Y %H:%M",
        "conditional_formatting": [
            {"column": "requests_failed", "operator": ">", "targetValue": 0, "colorScheme": "#E04355"},
        ],
    }),
    "dq_table": ("ops_data_quality", "Есть ли проблемы качества данных и как система их обработала?", "table", {
        "query_mode": "raw", "show_cell_bars": False, "all_columns": ["check_name", "check_type", "affected_rows", "system_action"],
        "order_by_cols": [], "row_limit": 100,
    }),
}

# ---------- дашборды: строки сетки (ключ графика, ширина из 12, высота) и фильтры ----------
DASHBOARDS = [
    {
        "slug": "food-prices",
        "title": "Цены на плодоовощную продукцию",
        "rows": [
            [("latest_table", 7, 60), ("norm_bar", 5, 60)],
            [("price_line", 12, 55)],
            [("norm_line", 6, 50), ("markup_line", 6, 50)],
            [("region_heatmap", 7, 70), ("fx_bar", 5, 70)],
        ],
        "filters": [
            # (id, название, датасет, колонка, значение по умолчанию, графики-исключения, множественный выбор)
            ("region", "Регион", "mart_price_monthly", "region_name", ["Российская Федерация"],
             ["region_heatmap", "fx_bar"], False),
            ("product", "Товар", "mart_price_monthly", "product_name", ["Картофель", "Огурцы", "Бананы"],
             ["latest_table", "norm_bar", "norm_line", "region_heatmap", "fx_bar"], True),
            ("product_one", "Товар для сравнения с нормой", "mart_price_monthly", "product_name", ["Картофель"],
             [k for k in ("latest_table", "norm_bar", "price_line", "markup_line", "region_heatmap", "fx_bar")],
             False),
        ],
        "time_filter": True,
    },
    {
        "slug": "ops",
        "title": "Операционный мониторинг конвейера данных",
        "rows": [
            [("freshness_table", 12, 40)],
            [("loads_by_status", 6, 50), ("rows_by_day", 6, 50)],
            [("loads_table", 12, 70)],
            [("dq_table", 12, 45)],
        ],
        "filters": [
            ("source", "Источник", "ops_load_log", "source_title", None, ["dq_table"], True),
        ],
        "time_filter": False,
    },
]


class Superset:
    def __init__(self, url: str):
        self.url = url
        self.s = requests.Session()

    def login(self) -> None:
        r = self.s.post(f"{self.url}/api/v1/security/login",
                        json={"username": ADMIN, "password": ADMIN_PWD, "provider": "db", "refresh": True})
        r.raise_for_status()
        self.s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        csrf = self.s.get(f"{self.url}/api/v1/security/csrf_token/").json()["result"]
        self.s.headers.update({"X-CSRFToken": csrf, "Referer": self.url})

    def call(self, method: str, path: str, **kw) -> dict:
        r = self.s.request(method, f"{self.url}/api/v1/{path}", **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path}: HTTP {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else {}

    def find(self, resource: str, col: str, value: str) -> dict | None:
        q = f"(filters:!((col:{col},opr:eq,value:'{value}')),page_size:100)"
        res = self.call("GET", f"{resource}/", params={"q": q})["result"]
        return res[0] if res else None


def ensure_database(api: Superset) -> int:
    body = {"database_name": DB_NAME, "sqlalchemy_uri": DB_URI, "expose_in_sqllab": True}
    found = api.find("database", "database_name", DB_NAME)
    if found:
        api.call("PUT", f"database/{found['id']}", json=body)
        return found["id"]
    return api.call("POST", "database/", json=body)["id"]


def wait_for_tables(api: Superset, db_id: int) -> None:
    """Витрины строит dbt в первом запуске DAG; до этого ждём."""
    deadline = time.time() + WAIT_TABLES_SEC
    while True:
        q = "(schema_name:marts,force:!t)"
        try:
            names = {t["value"] for t in api.call("GET", f"database/{db_id}/tables/", params={"q": q})["result"]}
        except RuntimeError:
            names = set()
        missing = [t for t in DATASETS if t not in names]
        if not missing:
            return
        if time.time() > deadline:
            raise RuntimeError(f"Витрины не появились: {missing}")
        print(f"Жду витрины {missing} (их создаёт dbt в DAG foodprices_pipeline)...", flush=True)
        time.sleep(30)


def ensure_dataset(api: Superset, db_id: int, table: str) -> int:
    q = f"(filters:!((col:table_name,opr:eq,value:'{table}'),(col:schema,opr:eq,value:marts)))"
    res = api.call("GET", "dataset/", params={"q": q})["result"]
    if res:
        ds_id = res[0]["id"]
        api.call("PUT", f"dataset/{ds_id}/refresh")          # подтянуть новые колонки витрины
    else:
        ds_id = api.call("POST", "dataset/", json={"database": db_id, "schema": "marts", "table_name": table})["id"]
    ds = api.call("GET", f"dataset/{ds_id}")["result"]
    cols = []
    for c in ds["columns"]:
        cols.append({"id": c["id"], "column_name": c["column_name"], "type": c.get("type"),
                     "is_dttm": c["column_name"] in ("period_month", "load_date", "started_msk", "last_data_date"),
                     "verbose_name": LABELS.get(c["column_name"]), "filterable": True, "groupby": True})
    main_dttm = next((c for c in ("period_month", "load_date") if any(x["column_name"] == c for x in cols)), None)
    api.call("PUT", f"dataset/{ds_id}", params={"override_columns": "true"},
             json={"columns": cols, "main_dttm_col": main_dttm,
                   "description": f"Витрина marts.{table} (строится dbt)."})
    return ds_id


def ensure_chart(api: Superset, key: str, ds_ids: dict[str, int]) -> int:
    table, name, viz, params = CHARTS[key]
    params = {"viz_type": viz, "datasource": f"{ds_ids[table]}__table", "adhoc_filters": [], **params}
    body = {"slice_name": name, "viz_type": viz, "datasource_id": ds_ids[table], "datasource_type": "table",
            "params": json.dumps(params, ensure_ascii=False), "description": key}
    found = api.find("chart", "slice_name", name)
    if found:
        api.call("PUT", f"chart/{found['id']}", json=body)
        return found["id"]
    return api.call("POST", "chart/", json=body)["id"]


def layout(title: str, rows: list, chart_ids: dict[str, int]) -> dict:
    pos = {"DASHBOARD_VERSION_KEY": "v2",
           "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
           "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
           "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": title}}}
    for i, row in enumerate(rows):
        rid = f"ROW-{i}"
        pos["GRID_ID"]["children"].append(rid)
        pos[rid] = {"type": "ROW", "id": rid, "children": [], "parents": ["ROOT_ID", "GRID_ID"],
                    "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        for key, width, height in row:
            cid = f"CHART-{key}"
            pos[rid]["children"].append(cid)
            pos[cid] = {"type": "CHART", "id": cid, "children": [], "parents": ["ROOT_ID", "GRID_ID", rid],
                        "meta": {"chartId": chart_ids[key], "width": width, "height": height,
                                 "sliceName": CHARTS[key][1]}}
    return pos


def native_filters(d: dict, ds_ids: dict[str, int], chart_ids: dict[str, int]) -> list[dict]:
    on_dash = [chart_ids[k] for row in d["rows"] for k, _, _ in row]
    out = []
    for fid, name, table, col, default, excluded, multi in d["filters"]:
        excl = [chart_ids[k] for k in excluded if k in chart_ids]
        mask = {"extraFormData": {}, "filterState": {}, "ownState": {}}
        if default:
            mask = {"extraFormData": {"filters": [{"col": col, "op": "IN", "val": default}]},
                    "filterState": {"value": default}, "ownState": {}}
        out.append({
            "id": f"NATIVE_FILTER-{fid}", "name": name, "filterType": "filter_select", "type": "NATIVE_FILTER",
            "targets": [{"datasetId": ds_ids[table], "column": {"name": col}}],
            "controlValues": {"multiSelect": multi, "enableEmptyFilter": False, "defaultToFirstItem": False,
                              "searchAllOptions": False, "inverseSelection": False},
            "defaultDataMask": mask, "cascadeParentIds": [],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": excl},
            "chartsInScope": [c for c in on_dash if c not in excl], "tabsInScope": [], "description": "",
        })
    if d.get("time_filter"):
        out.append({
            "id": "NATIVE_FILTER-period", "name": "Период", "filterType": "filter_time", "type": "NATIVE_FILTER",
            "targets": [{}], "controlValues": {"enableEmptyFilter": False},
            "defaultDataMask": {"extraFormData": {"time_range": "No filter"},
                                "filterState": {"value": "No filter"}, "ownState": {}},
            "cascadeParentIds": [], "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "chartsInScope": on_dash, "tabsInScope": [], "description": "",
        })
    return out


def ensure_dashboard(api: Superset, d: dict, ds_ids: dict[str, int], chart_ids: dict[str, int]) -> int:
    body = {
        "dashboard_title": d["title"], "slug": d["slug"], "published": True,
        "position_json": json.dumps(layout(d["title"], d["rows"], chart_ids), ensure_ascii=False),
        "json_metadata": json.dumps({
            "native_filter_configuration": native_filters(d, ds_ids, chart_ids),
            "refresh_frequency": 0, "color_scheme": "supersetColors", "cross_filters_enabled": False,
            "timed_refresh_immune_slices": [], "expanded_slices": {}, "label_colors": {},
            "shared_label_colors": [], "map_label_colors": {}, "color_scheme_domain": [],
        }, ensure_ascii=False),
    }
    found = api.find("dashboard", "slug", d["slug"])
    dash_id = api.call("PUT", f"dashboard/{found['id']}", json=body)["id"] if found \
        else api.call("POST", "dashboard/", json=body)["id"]
    for row in d["rows"]:
        for key, _, _ in row:
            api.call("PUT", f"chart/{chart_ids[key]}", json={"dashboards": [dash_id]})
    return dash_id


def main() -> int:
    api = Superset(URL)
    api.login()
    db_id = ensure_database(api)
    print(f"Подключение «{DB_NAME}»: id={db_id}", flush=True)
    wait_for_tables(api, db_id)
    api.login()                                              # токен мог истечь за время ожидания
    ds_ids = {t: ensure_dataset(api, db_id, t) for t in DATASETS}
    print(f"Датасеты: {ds_ids}", flush=True)
    chart_ids = {k: ensure_chart(api, k, ds_ids) for k in CHARTS}
    print(f"Графики: {len(chart_ids)}", flush=True)
    for d in DASHBOARDS:
        dash_id = ensure_dashboard(api, d, ds_ids, chart_ids)
        print(f"Дашборд «{d['title']}»: {URL}/superset/dashboard/{d['slug']}/ (id={dash_id})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
