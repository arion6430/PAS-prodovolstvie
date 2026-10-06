-- Операционная витрина: журнал загрузок в удобном для дашборда виде (время МСК, длительность, итог).
select
    l.load_id,
    l.run_id,
    case when l.run_id like 'scheduled__%' then 'по расписанию'
         when l.run_id like 'manual__%'    then 'вручную (Airflow)'
         else 'CLI' end                                                      as trigger_type,
    l.source,
    s.source_title,
    l.status,
    (l.started_at at time zone 'Europe/Moscow')::timestamp(0)                as started_msk,
    (l.started_at at time zone 'Europe/Moscow')::date                        as load_date,
    round(extract(epoch from l.finished_at - l.started_at)::numeric, 1)      as duration_sec,
    l.requests_total,
    l.requests_failed,
    l.rows_received,
    l.rows_inserted,
    l.rows_updated,
    l.rows_unchanged,
    jsonb_array_length(coalesce(l.warnings, '[]'::jsonb))                    as warnings_count,
    l.error
from {{ source('meta', 'load_log') }} l
left join {{ ref('source_sla') }} s using (source)
