"""Поведение HTTP-клиента при сбоях: повторы, ограничение частоты, неповторяемые ошибки."""
import pytest
import requests

from foodprices import http as http_mod
from foodprices.http import HttpClient, SourceUnavailable


class FakeResp:
    def __init__(self, status, headers=None):
        self.status_code = status
        self.headers = headers or {}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(http_mod.time, "sleep", lambda s: sleeps.append(s))
    return sleeps


def client_with(responses):
    c = HttpClient(retries=3, backoff_sec=1, min_interval_sec=0)
    seq = iter(responses)

    def fake_request(method, url, **kw):
        r = next(seq)
        if isinstance(r, Exception):
            raise r
        return r
    c.session.request = fake_request
    return c


def test_retries_then_succeeds(no_sleep):
    c = client_with([requests.Timeout("t"), FakeResp(503), FakeResp(200)])
    assert c.get("https://x").status_code == 200
    assert no_sleep == [1, 2]                         # экспоненциальная пауза


def test_respects_retry_after_on_429(no_sleep):
    c = client_with([FakeResp(429, {"Retry-After": "7"}), FakeResp(200)])
    c.get("https://x")
    assert no_sleep == [7]


def test_gives_up_after_retries():
    c = client_with([FakeResp(503)] * 3)
    with pytest.raises(SourceUnavailable, match="после 3 попыток"):
        c.get("https://x")


def test_client_error_is_not_retried(no_sleep):
    c = client_with([FakeResp(404)])
    with pytest.raises(SourceUnavailable, match="404"):
        c.get("https://x")
    assert no_sleep == []
