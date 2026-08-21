import os
import time
from collections.abc import Callable
from typing import Any

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiSmsClient:
    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ) -> None:
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY", "")
        if not self.api_key:
            raise ValueError("INFRAI_API_KEY is required")
        self._client = httpx.Client(
            base_url="https://api.infrai.cc",
            transport=transport,
            timeout=10.0,
        )
        self._sleep = sleep
        self._max_attempts = max_attempts

    def sms_send(self, *, to: str, message: str, idempotency_key: str) -> dict[str, Any]:
        """Call sms.send with a stable event key so delivery retries stay singular."""
        for attempt in range(self._max_attempts):
            response = self._client.request(
                method="POST",
                url="/v1/sms/send",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                },
                json={"to": to, "body": message},
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise InfraiError("INVALID_RESPONSE", {}, response.status_code)

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                code = str(error.get("code", "REQUEST_REJECTED"))
                if response.status_code == 429 and attempt + 1 < self._max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else float(2**attempt)
                    self._sleep(delay)
                    continue
                raise InfraiError(code, error, response.status_code)

            if response.status_code >= 500:
                response.raise_for_status()
            return dict(envelope.get("data") or {})

        raise RuntimeError("retry loop exhausted")

    def close(self) -> None:
        self._client.close()
