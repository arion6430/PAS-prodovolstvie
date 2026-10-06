"""Конфигурация Superset для локального стенда проекта (значения — из переменных окружения)."""
import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://superset:{os.environ['SUPERSET_DB_PASSWORD']}@postgres:5432/superset"
)

# интерфейс на русском
BABEL_DEFAULT_LOCALE = "ru"
LANGUAGES = {"ru": {"flag": "ru", "name": "Русский"}, "en": {"flag": "us", "name": "English"}}

FEATURE_FLAGS = {
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
}

# локальный стенд по http: без принудительного HTTPS и CSP
TALISMAN_ENABLED = False
WTF_CSRF_ENABLED = True
WTF_CSRF_EXEMPT_LIST = []

# простой кэш в памяти процесса (Redis для учебного стенда не нужен)
CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300}
DATA_CACHE_CONFIG = CACHE_CONFIG

ROW_LIMIT = 50000
