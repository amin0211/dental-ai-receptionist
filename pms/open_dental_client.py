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

    def parse_open_dental_appointment_datetime(
        self,
        value: str | None,
    ) -> str | None:
        """
        Converts Open Dental appointment datetime to ISO-like string.

        Example:
        2026-07-01 09:00:00 -> 2026-07-01T09:00:00
        """

        if not value:
            return None

        text = str(value).strip()

        if not text:
            return None

        if "T" in text:
            return text.replace("Z", "")

        if " " in text:
            return text.replace(" ", "T", 1)

        return text


    def parse_open_dental_appointment_duration_minutes(
        self,
        raw_appointment: dict[str, Any],
    ) -> int:
        """
        Estimates appointment duration from Open Dental appointment fields.

        Common Open Dental field:
        - Pattern: appointment time pattern. For MVP we treat each pattern char as 5 minutes.

        Fallback:
        - 30 minutes
        """

        # Some APIs may return explicit duration fields.
        explicit_values = [
            raw_appointment.get("Duration"),
            raw_appointment.get("duration"),
            raw_appointment.get("Length"),
            raw_appointment.get("length"),
            raw_appointment.get("Minutes"),
            raw_appointment.get("minutes"),
        ]

        for value in explicit_values:
            try:
                if value is not None and int(value) > 0:
                    return int(value)
            except Exception:
                pass

        pattern = raw_appointment.get("Pattern")

        if pattern:
            pattern_text = str(pattern).strip()

            # Ignore whitespace. Each visible pattern char is treated as one 5-minute unit.
            unit_count = len([ch for ch in pattern_text if not ch.isspace()])

            if unit_count > 0:
                minutes = unit_count * 5

                if minutes < 5:
                    return 30

                if minutes > 480:
                    return 480

                return minutes

        return 30


    def normalize_open_dental_appointment_status(
        self,
        raw_status: Any,
    ) -> str:
        """
        Maps Open Dental appointment status into our internal status.

        Our booking conflict logic currently treats status='confirmed' as busy.
        Cancelled/broken/deleted/unscheduled should not block time.
        """

        status = str(raw_status or "").strip().lower()

        if not status:
            return "confirmed"

        cancelled_values = [
            "cancelled",
            "canceled",
            "broken",
            "deleted",
            "unscheduled",
            "unsched",
        ]

        for value in cancelled_values:
            if value in status:
                return "cancelled"

        return "confirmed"


    def normalize_appointment(
        self,
        raw_appointment: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Converts Open Dental appointment into our normalized PMS appointment format.

        Open Dental common fields:
        - AptNum -> id
        - PatNum -> patient_external_id
        - ProvNum -> provider_external_id
        - AptDateTime -> start_time
        - Pattern -> duration
        - AptStatus -> status
        - ProcDescript -> service_name / reason
        - DateTStamp -> pms_updated_at
        """

        apt_num = raw_appointment.get("AptNum")

        start_time = self.parse_open_dental_appointment_datetime(
            raw_appointment.get("AptDateTime")
            or raw_appointment.get("DateTime")
            or raw_appointment.get("StartTime")
        )

        duration_minutes = self.parse_open_dental_appointment_duration_minutes(
            raw_appointment
        )

        service_name = (
            raw_appointment.get("ProcDescript")
            or raw_appointment.get("procDescript")
            or raw_appointment.get("ProcCode")
            or raw_appointment.get("procedure")
            or None
        )

        pat_num = raw_appointment.get("PatNum")
        prov_num = raw_appointment.get("ProvNum")

        return {
            "id": str(apt_num) if apt_num is not None else None,
            "patient_external_id": str(pat_num) if pat_num not in [None, 0, "0"] else None,
            "provider_external_id": str(prov_num) if prov_num not in [None, 0, "0"] else None,
            "start_time": start_time,
            "duration_minutes": duration_minutes,
            "status": self.normalize_open_dental_appointment_status(
                raw_appointment.get("AptStatus")
                or raw_appointment.get("aptStatus")
                or raw_appointment.get("Status")
            ),
            "service_name": service_name,
            "reason": service_name,
            "urgency": "normal",
            "pms_updated_at": raw_appointment.get("DateTStamp"),
            "raw": raw_appointment,
        }


    async def list_appointments(
        self,
        date_start: str | None = None,
        date_end: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Reads Open Dental appointments for a date range and returns normalized rows.
        """

        params: dict[str, Any] = {
            "Limit": limit,
            "Offset": offset,
        }

        if date_start:
            params["DateStart"] = date_start

        if date_end:
            params["DateEnd"] = date_end

        raw_appointments = await self.request(
            method="GET",
            path="/appointments",
            params=params,
        )

        if not isinstance(raw_appointments, list):
            return []

        normalized = []

        for raw_appointment in raw_appointments:
            item = self.normalize_appointment(raw_appointment)

            if not item.get("id"):
                continue

            if not item.get("start_time"):
                continue

            normalized.append(item)

        return normalized
    

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

        Open Dental ProcTime is not a direct minute value.
        For MVP, do not let a single X become a 10-minute service.

        Rule:
        - Empty/unknown -> 30 minutes
        - 1 or 2 X blocks -> 30 minutes
        - 3 X blocks -> 45 minutes
        - 4+ X blocks -> X count * 15 minutes
        """

        if not proc_time:
            return 30

        x_count = str(proc_time).upper().count("X")

        if x_count <= 0:
            return 30

        if x_count <= 2:
            return 30

        minutes = x_count * 15

        if minutes < 30:
            return 30

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
    
    def parse_open_dental_datetime_parts(
        self,
        value: str | None,
    ) -> tuple[str | None, str | None]:
        """
        Converts Open Dental datetime string into date and time parts.

        Example:
        2026-07-01 09:00:00 -> ("2026-07-01", "09:00:00")
        2026-07-01T09:00:00 -> ("2026-07-01", "09:00:00")
        """

        if not value:
            return None, None

        text = str(value).strip()

        if "T" in text:
            date_part, time_part = text.split("T", 1)
        elif " " in text:
            date_part, time_part = text.split(" ", 1)
        else:
            return text[:10], None

        time_part = time_part.replace("Z", "").split(".")[0]

        if len(time_part) == 5:
            time_part = f"{time_part}:00"

        return date_part[:10], time_part[:8]
    

    def normalize_availability_rule(
        self,
        raw_schedule: dict[str, Any],
        provider_external_id: str | None = None,
        external_id_suffix: str | None = None,
    ) -> dict[str, Any]:
        """
        Converts one Open Dental schedule entry into our normalized calendar rule format.

        Provider schedule:
        - rule_type = availability

        Blockout:
        - rule_type = lunch / meeting / vacation / blockout / ...
        - provider_external_id is resolved from operatory provider mapping.
        """

        schedule_num = raw_schedule.get("ScheduleNum")

        sched_date = self.normalize_open_dental_date(
            raw_schedule.get("SchedDate")
        )

        start_date = sched_date or self.normalize_open_dental_date(
            raw_schedule.get("StartTime")
        )

        end_date = sched_date or self.normalize_open_dental_date(
            raw_schedule.get("StopTime")
        )

        start_time = self.normalize_open_dental_time(
            raw_schedule.get("StartTime")
        )

        end_time = self.normalize_open_dental_time(
            raw_schedule.get("StopTime")
        )

        if not end_date:
            end_date = start_date

        if provider_external_id is None:
            prov_num = raw_schedule.get("ProvNum")
            provider_external_id = (
                str(prov_num)
                if prov_num not in [None, 0, "0"]
                else None
            )

        base_external_id = str(schedule_num) if schedule_num is not None else None

        if base_external_id and external_id_suffix:
            external_id = f"{base_external_id}:{external_id_suffix}"
        else:
            external_id = base_external_id

        rule_type = self.normalize_open_dental_rule_type(raw_schedule)

        return {
            "id": external_id,
            "provider_external_id": provider_external_id,
            "start_date": start_date,
            "end_date": end_date,
            "start_time": start_time,
            "end_time": end_time,
            "repeat_type": "none",
            "rule_type": rule_type,
            "is_active": True,
            "notes": (
                raw_schedule.get("blockoutType")
                or raw_schedule.get("Note")
                or raw_schedule.get("SchedType")
                or None
            ),
            "pms_updated_at": raw_schedule.get("DateTStamp"),
            "raw": raw_schedule,
        }
    
    async def list_availability_rules(
        self,
        date_start: str,
        date_end: str,
    ) -> list[dict[str, Any]]:
        """
        Reads Open Dental schedules for a date range.

        Imports:
        - Provider schedules as rule_type='availability'
        - Blockouts as rule_type='lunch', 'meeting', 'vacation', 'blockout', etc.

        Important:
        Open Dental blockouts are usually linked to operatories, not directly to providers.
        We map blockout operatories to providers using /operatories.
        """

        raw_schedules = await self.request(
            method="GET",
            path="/schedules",
            params={
                "dateStart": date_start,
                "dateEnd": date_end,
            },
        )

        if not isinstance(raw_schedules, list):
            return []

        operatory_provider_map = await self.build_operatory_provider_map()

        normalized: list[dict[str, Any]] = []

        for raw_schedule in raw_schedules:
            sched_type = str(raw_schedule.get("SchedType") or "").lower()

            # 1. Provider working schedule.
            if sched_type == "provider":
                prov_num = raw_schedule.get("ProvNum")

                if prov_num in [None, 0, "0"]:
                    continue

                item = self.normalize_availability_rule(
                    raw_schedule=raw_schedule,
                    provider_external_id=str(prov_num),
                )

                if not item.get("id"):
                    continue

                if not item.get("provider_external_id"):
                    continue

                if not item.get("start_date"):
                    continue

                if not item.get("start_time") or not item.get("end_time"):
                    continue

                normalized.append(item)
                continue

            # 2. Blockout schedule.
            if sched_type == "blockout":
                operatory_ids = self.parse_operatory_ids(
                    raw_schedule.get("operatories")
                )

                if not operatory_ids:
                    continue

                for operatory_id in operatory_ids:
                    provider_ids = operatory_provider_map.get(str(operatory_id)) or []

                    for provider_id in provider_ids:
                        item = self.normalize_availability_rule(
                            raw_schedule=raw_schedule,
                            provider_external_id=provider_id,
                            external_id_suffix=f"op:{operatory_id}:prov:{provider_id}",
                        )

                        if not item.get("id"):
                            continue

                        if not item.get("provider_external_id"):
                            continue

                        if not item.get("start_date"):
                            continue

                        if not item.get("start_time") or not item.get("end_time"):
                            continue

                        # Safety: blockouts must not become availability.
                        if item.get("rule_type") == "availability":
                            item["rule_type"] = "blockout"

                        normalized.append(item)

        return normalized
    
    def normalize_open_dental_time(
        self,
        value: str | None,
    ) -> str | None:
        """
        Converts Open Dental time value into HH:MM:SS.
        Examples:
        08:00:00 -> 08:00:00
        08:00 -> 08:00:00
        2026-07-01 08:00:00 -> 08:00:00
        """

        if not value:
            return None

        text = str(value).strip()

        if "T" in text:
            text = text.split("T", 1)[1]

        if " " in text:
            text = text.split(" ", 1)[1]

        text = text.replace("Z", "").split(".")[0]

        if len(text) == 5:
            text = f"{text}:00"

        if len(text) >= 8:
            return text[:8]

        return None

    def normalize_open_dental_date(
        self,
        value: str | None,
    ) -> str | None:
        """
        Converts Open Dental date/datetime into YYYY-MM-DD.
        """

        if not value:
            return None

        text = str(value).strip()

        if "T" in text:
            return text.split("T", 1)[0][:10]

        if " " in text:
            return text.split(" ", 1)[0][:10]

        return text[:10]

    def parse_operatory_ids(
        self,
        operatories_value: Any,
    ) -> list[str]:
        """
        Open Dental schedules may return operatories as a comma-separated string.
        Example:
        "5"
        "5,6"
        """

        if operatories_value is None:
            return []

        if isinstance(operatories_value, list):
            return [
                str(item).strip()
                for item in operatories_value
                if str(item).strip()
            ]

        text = str(operatories_value).strip()

        if not text:
            return []

        return [
            part.strip()
            for part in text.split(",")
            if part.strip()
        ]

    def normalize_open_dental_rule_type(
        self,
        raw_schedule: dict[str, Any],
    ) -> str:
        """
        Maps Open Dental blockout label into our internal rule_type.

        Only 'availability' opens time.
        Any other rule_type is treated as blocked time by our booking logic.
        """

        sched_type = str(raw_schedule.get("SchedType") or "").lower()
        blockout_name = str(raw_schedule.get("blockoutType") or "").lower()
        note = str(raw_schedule.get("Note") or "").lower()

        combined = f"{blockout_name} {note}".strip()

        if sched_type == "provider":
            return "availability"

        if "lunch" in combined:
            return "lunch"

        if "vacation" in combined or "holiday" in combined:
            return "vacation"

        if "meeting" in combined:
            return "meeting"

        if "training" in combined:
            return "training"

        if "closed" in combined:
            return "clinic_closed"

        if "personal" in combined:
            return "personal"

        return "blockout"
    
    async def list_operatories(self) -> list[dict[str, Any]]:
        raw_operatories = await self.request(
            method="GET",
            path="/operatories",
        )

        if not isinstance(raw_operatories, list):
            return []

        return raw_operatories

    async def build_operatory_provider_map(self) -> dict[str, list[str]]:
        """
        Builds:
        {
          "5": ["2"],
          "6": ["3"]
        }

        Open Dental Operatory:
        - OperatoryNum
        - ProvDentist
        - ProvHygienist
        """

        operatories = await self.list_operatories()

        mapping: dict[str, list[str]] = {}

        for operatory in operatories:
            op_num = operatory.get("OperatoryNum")

            if op_num is None:
                continue

            provider_ids: list[str] = []

            prov_dentist = operatory.get("ProvDentist")
            prov_hygienist = operatory.get("ProvHygienist")

            if prov_dentist not in [None, 0, "0"]:
                provider_ids.append(str(prov_dentist))

            if prov_hygienist not in [None, 0, "0"]:
                provider_ids.append(str(prov_hygienist))

            mapping[str(op_num)] = provider_ids

        return mapping
    
