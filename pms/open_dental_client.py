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
    Open Dental REST API client.

    Company-level values:
    - OPEN_DENTAL_BASE_URL
    - OPEN_DENTAL_DEVELOPER_KEY

    Per-clinic value:
    - customer_key from pms_connections.credentials
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

        async with httpx.AsyncClient(timeout=45) as client:
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
        """
        Converts Open Dental patient object into our normalized PMS patient format.

        Open Dental:
        - PatNum -> id
        - FName -> first_name
        - LName -> last_name
        - Preferred -> preferred_name
        - Birthdate -> birthdate
        - DateTStamp -> pms_updated_at
        """

        pat_num = raw_patient.get("PatNum")

        phone_primary = (
            raw_patient.get("WirelessPhone")
            or raw_patient.get("HmPhone")
            or raw_patient.get("WkPhone")
            or ""
        )

        phone_secondary = None

        if raw_patient.get("WirelessPhone"):
            phone_secondary = raw_patient.get("HmPhone") or raw_patient.get("WkPhone")
        else:
            phone_secondary = raw_patient.get("WkPhone")

        pat_status = raw_patient.get("PatStatus") or "Patient"

        if str(pat_status).lower() == "patient":
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

            # Open Dental change timestamp.
            # This is what we use for incremental sync.
            "pms_updated_at": raw_patient.get("DateTStamp"),

            "raw": raw_patient,
        }

    def normalize_provider(self, raw_provider: dict[str, Any]) -> dict[str, Any]:
        """
        Converts Open Dental provider object into our normalized PMS doctor format.

        Open Dental common fields:
        - ProvNum -> id
        - FName / LName -> full_name
        - Abbr -> display_name
        - Specialty -> specialty
        - IsHidden -> is_active false
        - DateTStamp -> pms_updated_at
        """

        prov_num = raw_provider.get("ProvNum")

        first_name = raw_provider.get("FName") or ""
        last_name = raw_provider.get("LName") or ""
        abbreviation = raw_provider.get("Abbr") or ""

        full_name = " ".join(
            part for part in [first_name, last_name] if part
        ).strip()

        if not full_name:
            full_name = abbreviation or f"Provider {prov_num}"

        display_name = abbreviation or full_name

        is_hidden = raw_provider.get("IsHidden")

        is_active = True

        if is_hidden is True:
            is_active = False
        elif str(is_hidden).lower() in ["true", "1", "yes"]:
            is_active = False

        return {
            "id": str(prov_num) if prov_num is not None else None,
            "full_name": full_name,
            "display_name": display_name,
            "title": "Dr.",
            "specialty": raw_provider.get("Specialty") or None,
            "phone_number": raw_provider.get("Phone") or None,
            "email": raw_provider.get("Email") or None,
            "is_active": is_active,
            "pms_updated_at": raw_provider.get("DateTStamp"),
            "raw": raw_provider,
        }
    
    async def test_connection(self) -> dict[str, Any]:
        """
        Test API access using the faster patient list endpoint.
        """

        data = await self.request(
            method="GET",
            path="/patients/Simple",
            params={"Offset": 0},
        )

        sample = data[:1] if isinstance(data, list) else data

        return {
            "ok": True,
            "pms_type": "open_dental",
            "base_url": self.base_url,
            "sample_response": sample,
        }

    async def list_patients(
        self,
        limit: int = 50,
        offset: int = 0,
        date_tstamp: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Backward-compatible simple patient list.

        Used by the current /pms/import-patients route.
        For real sync, prefer list_patients_page().
        """

        page = await self.list_patients_page(
            offset=offset,
            date_tstamp=date_tstamp,
        )

        return page["patients"][:limit]

    async def list_patients_page(
        self,
        offset: int = 0,
        date_tstamp: str | None = None,
    ) -> dict[str, Any]:
        """
        Reads one page of patients from Open Dental.

        Uses:
        - /patients/Simple
        - Offset for paging
        - DateTStamp for incremental sync

        Returns normalized patients plus paging/cursor metadata.
        """

        params: dict[str, Any] = {
            "Offset": offset,
        }

        if date_tstamp:
            params["DateTStamp"] = date_tstamp

        raw_patients = await self.request(
            method="GET",
            path="/patients/Simple",
            params=params,
        )

        if not isinstance(raw_patients, list):
            raw_patients = []

        patients = [
            self.normalize_patient(raw_patient)
            for raw_patient in raw_patients
        ]

        pms_updated_values = [
            patient.get("pms_updated_at")
            for patient in patients
            if patient.get("pms_updated_at")
        ]

        max_pms_updated_at = (
            max(pms_updated_values)
            if pms_updated_values
            else None
        )

        raw_count = len(raw_patients)

        return {
            "patients": patients,
            "raw_count": raw_count,
            "offset": offset,
            "next_offset": offset + raw_count,
            "has_more": raw_count > 0,
            "max_pms_updated_at": max_pms_updated_at,
            "date_tstamp": date_tstamp,
        }

    async def get_patient(self, external_patient_id: str) -> dict[str, Any]:
        raw_patient = await self.request(
            method="GET",
            path=f"/patients/{external_patient_id}",
        )

        if not isinstance(raw_patient, dict):
            return {
                "id": external_patient_id,
                "raw": raw_patient,
            }

        return self.normalize_patient(raw_patient)

    async def list_appointments(
        self,
        date_start: str | None = None,
        date_end: str | None = None,
        limit: int = 50,
    ) -> Any:
        params: dict[str, Any] = {
            "Limit": limit,
        }

        if date_start:
            params["DateStart"] = date_start

        if date_end:
            params["DateEnd"] = date_end

        return await self.request(
            method="GET",
            path="/appointments",
            params=params,
        )

    async def list_providers(self) -> list[dict[str, Any]]:
        raw_providers = await self.request(
            method="GET",
            path="/providers",
        )

        if not isinstance(raw_providers, list):
            return []

        return [
            self.normalize_provider(provider)
            for provider in raw_providers
        ]
    
    def make_slug(self, value: str | None) -> str:
        if not value:
            return "unknown"

        slug = str(value).strip().lower()

        cleaned = []

        previous_dash = False

        for ch in slug:
            if ch.isalnum():
                cleaned.append(ch)
                previous_dash = False
            else:
                if not previous_dash:
                    cleaned.append("-")
                    previous_dash = True

        slug = "".join(cleaned).strip("-")

        return slug or "unknown"
    
    def parse_open_dental_proc_time_minutes(
        self,
        proc_time: str | None,
    ) -> int:
        """
        Converts Open Dental ProcTime pattern into approximate minutes.

        MVP rule:
        - Count X characters as time units.
        - Each X = 10 minutes.
        - Fallback = 30 minutes.
        """

        if not proc_time:
            return 30

        x_count = str(proc_time).upper().count("X")

        if x_count <= 0:
            return 30

        minutes = x_count * 10

        if minutes < 10:
            return 10

        if minutes > 240:
            return 240

        return minutes
    
    def normalize_service_group(self, raw_group: dict[str, Any]) -> dict[str, Any]:
        """
        Converts Open Dental definition row into our normalized service group format.

        Open Dental:
        - DefNum -> id/code
        - ItemName -> name
        - Category = 11 means procedure code category
        """

        def_num = raw_group.get("DefNum")

        name = (
            raw_group.get("ItemName")
            or raw_group.get("Name")
            or raw_group.get("Description")
            or f"Group {def_num}"
        )

        code = str(def_num) if def_num is not None else None

        return {
            "id": str(def_num) if def_num is not None else None,
            "code": code,
            "name": name,
            "slug": self.make_slug(name),
            "description": raw_group.get("ItemValue") or None,
            "is_active": True,
            "sort_order": raw_group.get("ItemOrder") or 0,
            "pms_updated_at": raw_group.get("DateTStamp"),
            "raw": raw_group,
        }    

    async def list_service_groups(self) -> list[dict[str, Any]]:
        """
        Reads Open Dental procedure code categories from definitions.

        Open Dental procedure code categories are definitions where Category = 11.
        """

        raw_groups = await self.request(
            method="GET",
            path="/definitions",
            params={
                "Category": 11,
            },
        )

        if not isinstance(raw_groups, list):
            return []

        return [
            self.normalize_service_group(group)
            for group in raw_groups
        ]
    
    def normalize_service(self, raw_service: dict[str, Any]) -> dict[str, Any]:
        """
        Converts Open Dental procedure code into our normalized service format.

        Open Dental:
        - CodeNum -> external_id
        - ProcCode -> code shown to user, e.g. D1110
        - Descript -> name
        - ProcCat -> Open Dental definition.DefNum, used only to link service_group_id
        - ProcTime -> default_duration_minutes
        """

        code_num = raw_service.get("CodeNum")
        proc_code = raw_service.get("ProcCode")

        description = (
            raw_service.get("Descript")
            or raw_service.get("AbbrDesc")
            or proc_code
            or f"Procedure {code_num}"
        )

        duration_minutes = self.parse_open_dental_proc_time_minutes(
            raw_service.get("ProcTime")
        )

        proc_cat = raw_service.get("ProcCat")

        return {
            "id": str(code_num) if code_num is not None else None,
            "code": proc_code,
            "name": description,
            "canonical_reason": description,
            "description": raw_service.get("AbbrDesc") or description,

            # This is not saved directly into service_categories.
            # It is only used by backend to find service_groups.id.
            "group_external_id": str(proc_cat) if proc_cat is not None else None,

            "default_duration_minutes": duration_minutes,
            "default_urgency": "normal",

            # Imported PMS services should not automatically become AI-bookable.
            "is_active": False,
            "creates_appointment_request": False,

            "pms_updated_at": raw_service.get("DateTStamp"),
            "raw": raw_service,
        }
    
    async def list_services(self) -> list[dict[str, Any]]:
        raw_services = await self.request(
            method="GET",
            path="/procedurecodes",
        )

        if not isinstance(raw_services, list):
            return []

        return [
            self.normalize_service(service)
            for service in raw_services
        ]