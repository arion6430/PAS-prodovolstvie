"""Тесты разбора ответов источников на небольших образцах реального формата."""
import json

import pytest

from foodprices.sources.base import Payload, SchemaChanged
from foodprices.sources.cbr import CbrFx, CbrKeyRate
from foodprices.sources.emiss import EmissProducer, EmissRetail, FedstatIndicator, parse_sdmx, strip_header
from foodprices.sources.openmeteo import OpenMeteo

SDMX = """<?xml version="1.0" encoding="utf-8"?>
<GenericData xmlns="http://www.SDMX.org/resources/SDMXML/schemas/v1_0/message"
 xmlns:generic="http://www.SDMX.org/resources/SDMXML/schemas/v1_0/generic"
 xmlns:structure="http://www.SDMX.org/resources/SDMXML/schemas/v1_0/structure">
<Header Id="h"><ID>{id}</ID><Prepared>{ts}</Prepared></Header>
<CodeLists>
 <structure:CodeList id="s_OKATO"><structure:Code value="643">
  <structure:Description xml:lang="ru">Российская Федерация</structure:Description></structure:Code></structure:CodeList>
 <structure:CodeList id="s_grtov"><structure:Code value="2501">
  <structure:Description xml:lang="ru">Картофель, кг</structure:Description></structure:Code></structure:CodeList>
</CodeLists>
<DataSet>
 <generic:Series>
  <generic:SeriesKey><generic:Value concept="s_OKATO" value="643"/><generic:Value concept="s_grtov" value="2501"/></generic:SeriesKey>
  <generic:Attributes><generic:Value concept="EI" value="рубль"/><generic:Value concept="PERIOD" value="январь"/></generic:Attributes>
  <generic:Obs><generic:Time>2019</generic:Time><generic:ObsValue value="25,79"/></generic:Obs>
 </generic:Series>
</DataSet></GenericData>"""


def sdmx(id_="1", ts="2026-10-06T20:00:00") -> bytes:
    return SDMX.format(id=id_, ts=ts).encode("utf-8")


def test_parse_sdmx_decodes_codes_and_values():
    df = parse_sdmx(sdmx())
    row = df.iloc[0]
    assert row["s_OKATO_name"] == "Российская Федерация"
    assert row["s_grtov_name"] == "Картофель, кг"
    assert (row["PERIOD"], row["TIME"], row["VALUE"]) == ("январь", "2019", "25,79")


def test_strip_header_makes_fingerprint_stable():
    """Одинаковые данные с разным временем формирования должны давать одинаковый отпечаток."""
    assert strip_header(sdmx("1", "2026-01-01")) == strip_header(sdmx("2", "2026-10-06"))


def test_emiss_retail_parse_keeps_raw_text():
    src = EmissRetail({}, http=None)
    df = src.parse(Payload(sdmx(), b"", "xml"))
    assert list(df.columns) == ["okato_code", "okato_name", "good_code", "good_name", "unit",
                                "year", "period_name", "value"]
    assert df.iloc[0]["value"] == "25,79"           # тип приводится в staging, raw хранит как в источнике


def test_emiss_producer_detects_schema_change():
    """В ответе для 57693 нет измерения ОКПД2 — это изменение схемы, загрузка должна упасть явно."""
    with pytest.raises(SchemaChanged):
        EmissProducer({}, http=None).parse(Payload(sdmx(), b"", "xml"))


FEDSTAT_HTML = """
<input type="hidden" name="token" value="TOKEN123" />
filters: {
                            0: {
                                title: 'Показатель',
                                values: {
                                    31448: {
                                        title: 'Цены',
                                        order: 0
                                    }
                                }
                            },
                            3: {
                                title: 'Год',
                                values: {
                                    '2025': { title: '2025' },
                                    '2026': { title: '2026' }
                                }
                            },
                            58273: {
                                title: 'Виды товаров и услуг',
                                values: {
                                    1743470: { title: 'Картофель, кг' }
                                }
                            }
                        },
                        left_columns: [ 58273 ],
                        top_columns: [ 3 ],
"""


def test_fedstat_indicator_form():
    ind = FedstatIndicator(FEDSTAT_HTML)
    assert ind.token == "TOKEN123"
    assert ind.find_filter("Год") == "3"
    form, warnings = ind.form(31448, {"3": {"2026"}, "58273": {"Картофель, кг", "Морковь, кг"}})
    selected = [v for k, v in form if k == "selectedFilterIds"]
    assert selected == ["0_31448", "3_2026", "58273_1743470"]
    assert ("lineObjectIds", "0") in form and ("columnObjectIds", "3") in form
    assert warnings and "Морковь, кг" in warnings[0]        # пропавшее значение справочника — предупреждение


def test_cbr_fx_parse():
    xml = ('<?xml version="1.0" encoding="windows-1251"?><ValCurs ID="R01235">'
           '<Record Date="01.01.2000" Id="R01235"><Nominal>1</Nominal><Value>27,0000</Value></Record>'
           '</ValCurs>').encode("cp1251")
    df = CbrFx({"currencies": {"R01235": "USD"}}, http=None).parse(Payload(xml, xml, "xml"))
    assert df.to_dict("records") == [{"currency_id": "R01235", "char_code": "USD", "rate_date": "01.01.2000",
                                      "nominal": "1", "value": "27,0000"}]


def test_cbr_key_rate_parse():
    html = '<table class="data"><tr><th>Дата</th></tr><tr>\n<td>05.10.2026</td>\n<td>14,00</td>\n</tr></table>'
    df = CbrKeyRate({}, http=None).parse(Payload(html.encode(), b"", "html"))
    assert df.to_dict("records") == [{"rate_date": "05.10.2026", "rate": "14,00"}]


def test_openmeteo_parse_drops_empty_days():
    data = {"point_id": "moscow", "daily": {"time": ["2026-10-05", "2026-10-06"],
                                            "temperature_2m_mean": [10.5, None],
                                            "precipitation_sum": [0.0, None]}}
    src = OpenMeteo({"variables": ["temperature_2m_mean", "precipitation_sum"]}, http=None)
    df = src.parse(Payload(json.dumps(data).encode(), b"", "json"))
    assert df["obs_date"].tolist() == ["2026-10-05"]
