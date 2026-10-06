"""오류 출력에서 인증 정보와 요청 URL을 제거한다."""

import os
import re
from urllib.parse import quote, quote_plus


def redact(text: str) -> str:
    """환경 변수의 비밀값과 이름이 붙은 인증 정보를 숨긴다."""
    for key, value in os.environ.items():
        if len(value) < 4 or not any(word in key.upper() for word in
                                     ("TOKEN", "SECRET", "PASSWORD", "API_KEY")):
            continue
        for encoded in {value, quote(value, safe=""), quote_plus(value)}:
            text = text.replace(encoded, "[숨김]")
    return re.sub(
        r"(?i)\b(access_token|refresh_token|client_secret|api_key|auth_token|password)"
        r"(\s*[\"']?\s*[:=]\s*[\"']?)([^&\s\"',;)]+)",
        lambda match: f"{match[1]}{match[2]}[숨김]", text,
    )


def safe_error(exc: Exception) -> str:
    """HTTP 오류는 상태 코드만 보여 주고 응답 본문·URL은 출력하지 않는다."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return f"API 요청이 실패했습니다 (HTTP {status})."
    return redact(str(exc))
