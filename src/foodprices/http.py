"""HTTP-клиент с таймаутами, повторами, экспоненциальной паузой и ограничением частоты запросов."""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class SourceUnavailable(RuntimeError):
    """Источник недоступен (после всех повторов или из-за неповторяемой ошибки)."""


class HttpClient:
    def __init__(self, timeout_sec: float = 120, retries: int = 4, backoff_sec: float = 5,
                 min_interval_sec: float = 1.0, user_agent: str = "Mozilla/5.0"):
        self.timeout = timeout_sec
        self.retries = retries
        self.backoff = backoff_sec
        self.min_interval = min_interval_sec
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self._last_call: dict[str, float] = {}

    @classmethod
    def from_config(cls, cfg: dict) -> "HttpClient":
        return cls(**cfg)

    def _throttle(self, url: str) -> None:
        """Не чаще одного запроса к хосту в min_interval секунд."""
        host = urlparse(url).netloc
        wait = self._last_call.get(host, 0) + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_call[host] = time.monotonic()

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        last_error = "нет попыток"
        for attempt in range(1, self.retries + 1):
            self._throttle(url)
            pause = self.backoff * 2 ** (attempt - 1)
            try:
                resp = self.session.request(method, url, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = f"{type(e).__name__}: {e}"
            else:
                if resp.status_code in RETRY_STATUS:
                    last_error = f"HTTP {resp.status_code}"
                    retry_after = resp.headers.get("Retry-After", "")
                    if retry_after.isdigit():  # 429: сервер сам сообщает, сколько ждать
                        pause = float(retry_after)
                elif resp.status_code >= 400:
                    raise SourceUnavailable(f"{method} {url}: HTTP {resp.status_code}")
                else:
                    return resp
            if attempt < self.retries:
                log.warning("%s %s: попытка %d/%d не удалась (%s), пауза %.0f с",
                            method, url, attempt, self.retries, last_error, pause)
                time.sleep(pause)
        raise SourceUnavailable(f"{method} {url}: {last_error} (после {self.retries} попыток)")

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)
