"""GUI와 CLI의 인증 정보는 같은 macOS 키체인 항목을 사용한다."""

import json
import sys
from .store import AppError


class KeychainVault:
    service = "WhosekeyLabs.PublishSocial"

    def backend(self):
        if sys.platform != "darwin":
            raise AppError("현재 인증 정보 저장은 macOS 키체인을 지원합니다.")
        from keyring.backends.macOS import Keyring
        return Keyring()

    def get(self, account_id):
        try:
            value = self.backend().get_password(self.service, account_id)
            return json.loads(value) if value else {}
        except AppError:
            raise
        except Exception:
            raise AppError("키체인에서 인증 정보를 읽지 못했습니다. 접근 권한을 확인하세요.") from None

    def set(self, account_id, values):
        try:
            self.backend().set_password(self.service, account_id, json.dumps(values))
        except AppError:
            raise
        except Exception:
            raise AppError("키체인에 인증 정보를 저장하지 못했습니다.") from None
