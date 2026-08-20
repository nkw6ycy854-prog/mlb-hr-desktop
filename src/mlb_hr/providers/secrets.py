from __future__ import annotations

SERVICE = "MLBHRDesktop"


class SecretStore:
    def __init__(self) -> None:
        try:
            import keyring
        except Exception as exc:
            self._keyring = None
            self._error = exc
        else:
            self._keyring = keyring
            self._error = None

    def get(self, key: str) -> str | None:
        if self._keyring is None:
            return None
        try:
            return self._keyring.get_password(SERVICE, key)
        except Exception:
            return None

    def set(self, key: str, value: str) -> bool:
        if self._keyring is None:
            return False
        try:
            self._keyring.set_password(SERVICE, key, value)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        if self._keyring is None:
            return False
        try:
            self._keyring.delete_password(SERVICE, key)
            return True
        except Exception:
            return False
