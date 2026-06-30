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


    def normalize_patient(self, raw_patient: dict[str, Any]) -> dict[str, Any]:
        pat_num = raw_patient.get("PatNum")

        phone_primary = (
            raw_patient.get("WirelessPhone")
            or raw_patient.get("HmPhone")
            or raw_patient.get("WkPhone")
            or ""
        )

        phone_secondary = (
            raw_patient.get("HmPhone")
            if raw_patient.get("WirelessPhone")
            else raw_patient.get("WkPhone")
        )

        pat_status = raw_patient.get("PatStatus") or "Patient"

        if pat_status == "Patient":
            status = "active"
        else:
            status = str(pat_status).lower()

        return {
            "id": str(pat_num) if pat_num is not None else None,
            "first_name": raw_patient.get("FName") or "",
            "last_name": raw_patient.get("LName") or "",
            "preferred_name": raw_patient.get("Preferred") or "",
            "phone": phone_primary,
            "phone_secondary": phone_secondary or None,
            "email": raw_patient.get("Email") or None,
            "birthdate": raw_patient.get("Birthdate") or None,
            "status": status,
            "address_line1": raw_patient.get("Address") or None,
            "address_line2": raw_patient.get("Address2") or None,
            "city": raw_patient.get("City") or None,
            "province": raw_patient.get("State") or None,
            "postal_code": raw_patient.get("Zip") or None,
            "country": "USA",
            "raw": raw_patient,
        }
    

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

    async def list_patients(self, limit: int = 50) -> list[dict[str, Any]]:
        raw_patients = await self.request(
            method="GET",
            path="/patients",
            params={"Limit": limit},
        )

        return [self.normalize_patient(patient) for patient in raw_patients]

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