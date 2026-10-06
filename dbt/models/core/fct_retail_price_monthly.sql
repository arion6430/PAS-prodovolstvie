-- Средняя потребительская цена, руб/кг: товар × регион × месяц в единых ключах.
{{ resolve_entities('stg_emiss__retail_prices', 'emiss_retail', 'good_code') }}
