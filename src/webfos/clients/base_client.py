"""
외부 API 호출 공통 베이스 클라이언트.

타임아웃, 재시도, 에러 핸들링을 공통으로 처리한다.
모든 외부 서비스별 클라이언트는 이 클래스를 상속한다.
"""

import httpx
from loguru import logger
from typing import Any, Dict, Optional


class ExternalServiceError(Exception):
    """외부 서비스 호출 실패 시 발생하는 예외"""
    def __init__(self, service: str, status_code: int = 0, detail: str = ""):
        self.service = service
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{service}] {status_code}: {detail}")


class BaseClient:
    """
    외부 API 호출 공통 베이스.

    - 지연 초기화된 httpx.AsyncClient
    - 공통 타임아웃 / 헤더 / 에러 핸들링
    - 재시도 로직 (max_retries)
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        max_retries: int = 2,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._default_headers = headers or {}
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """지연 초기화된 HTTP 클라이언트 반환"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self._default_headers,
            )
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        공통 요청 처리.

        - 재시도 (max_retries 횟수만큼)
        - 타임아웃 에러 래핑
        - 비정상 응답 시 ExternalServiceError 발생
        - 응답을 Dict로 변환하여 반환
        """
        client = await self._get_client()
        last_error = None
        service_name = self.__class__.__name__

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.request(method, path, **kwargs)

                if response.status_code >= 400:
                    raise ExternalServiceError(
                        service=service_name,
                        status_code=response.status_code,
                        detail=response.text[:500],
                    )

                return response.json()

            except ExternalServiceError:
                raise
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(
                    f"[{service_name}] 타임아웃 (attempt {attempt}/{self.max_retries}): "
                    f"{method} {path}"
                )
            except httpx.HTTPError as e:
                last_error = e
                logger.warning(
                    f"[{service_name}] HTTP 에러 (attempt {attempt}/{self.max_retries}): {e}"
                )

        raise ExternalServiceError(
            service=service_name,
            detail=f"최대 재시도 횟수 초과: {last_error}",
        )

    async def close(self):
        """클라이언트 리소스 정리 — lifespan 종료 시 호출"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
