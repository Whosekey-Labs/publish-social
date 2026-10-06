"""전 회귀 검증에서 실제 외부 API 호출을 금지한다."""

import pytest
import requests


@pytest.fixture(autouse=True)
def 외부_API_차단(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("실제 외부 API를 호출하는 검증은 허용하지 않습니다.")
    monkeypatch.setattr(requests.sessions.Session, "request", denied)
