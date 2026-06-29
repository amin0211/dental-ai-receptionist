import os
from typing import Any

import httpx

from pms.base import PmsApiError, PmsClient


OPEN_DENTAL_BASE_URL = os.environ.get(
    "OPEN_DENTAL_BASE_URL",
    "https://api.opendental.com/api/v1",
).rstrip("/")

OPEN_DENTAL_DEVELOPER_KEY = os.environ.get("OPEN_DENTAL_DEVELOPER_KEY")


class OpenDentalClient(PmsClient):
    """
    Client for Open Dental REST API.

    ثابت‌های شرکت:
    - OPEN_DENTAL_BASE_URL
    - OPEN_DENTAL_DEVELOPER_KEY

    مخصوص هر کلینیک:
    - customer_key از pms_connections.credentials
    """

    def __init__(
        self,
        customer_key: str,
        base_url: str | None = None,
        developer_key: str | None = None,
    ):
        self.base_url = (base_url or OPEN_DENTAL_BASE_URL).rstrip("/")
        self.developer_key = developer_key or OPEN_DENTAL_DEVELOPER_KEY
        self.customer_key = customer_key

        if not self.developer_key:
            raise ValueError("OPEN_DENTAL_DEVELOPER_KEY is missing")

        if not self.customer_key:
            raise ValueError("Open Dental customer_key is missing")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"ODFHIR {self.developer_key}/{self.customer_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self._headers(),
                params=params,
                json=json,
            )

        try:
            response_body = response.json()
        except Exception:
            response_body = response.text

        if response.status_code >= 400:
            raise PmsApiError(
                status_code=response.status_code,
                message=f"Open Dental API error: {response.status_code}",
                response_body=response_body,
            )

        return response_body

    async def test_connection(self) -> dict[str, Any]:
        data = await self.request(
            method="GET",
            path="/patients",
            params={"Limit": 1},
        )

        return {
            "ok": True,
            "pms_type": "open_dental",
            "base_url": self.base_url,
            "sample_response": data,
        }

    async def list_patients(self, limit: int = 50) -> Any:
        return await self.request(
            method="GET",
            path="/patients",
            params={"Limit": limit},
        )

    async def get_patient(self, external_patient_id: str) -> Any:
        return await self.request(
            method="GET",
            path=f"/patients/{external_patient_id}",
        )

    async def list_appointments(
        self,
        date_start: str | None = None,
        date_end: str | None = None,
        limit: int = 50,
    ) -> Any:
        params: dict[str, Any] = {"Limit": limit}

        if date_start:
            params["DateStart"] = date_start

        if date_end:
            params["DateEnd"] = date_end

        return await self.request(
            method="GET",
            path="/appointments",
            params=params,
        )

    async def list_providers(self) -> Any:
        return await self.request(
            method="GET",
            path="/providers",
        )