from datetime import date, datetime, timedelta, timezone
from typing import Any

from pms.base import PmsClient


class MockPmsClient(PmsClient):
    """
    Mock PMS client for local/dev testing.

    This client does not call any external API.
    It returns fake but realistic dental PMS data.
    """

    def __init__(self):
        self.today = date.today()

    async def test_connection(self) -> dict[str, Any]:
        return {
            "ok": True,
            "pms_type": "mock",
            "message": "Mock PMS connection is working.",
        }

    async def list_patients(self, limit: int = 50) -> list[dict[str, Any]]:
        patients = [
            {
                "id": "mock-patient-1001",
                "first_name": "Amin",
                "last_name": "Yavari",
                "preferred_name": "Amin",
                "phone": "7788723613",
                "email": "amin@example.com",
                "birthdate": "1990-05-15",
                "status": "active",
                "raw": {
                    "MockPatNum": "mock-patient-1001",
                    "FName": "Amin",
                    "LName": "Yavari",
                    "WirelessPhone": "7788723613",
                },
            },
            {
                "id": "mock-patient-1002",
                "first_name": "Sara",
                "last_name": "Ahmadi",
                "preferred_name": "Sara",
                "phone": "6045551234",
                "email": "sara@example.com",
                "birthdate": "1988-09-22",
                "status": "active",
                "raw": {
                    "MockPatNum": "mock-patient-1002",
                    "FName": "Sara",
                    "LName": "Ahmadi",
                    "WirelessPhone": "6045551234",
                },
            },
            {
                "id": "mock-patient-1003",
                "first_name": "David",
                "last_name": "Chen",
                "preferred_name": "David",
                "phone": "7785550199",
                "email": "david@example.com",
                "birthdate": "1979-02-10",
                "status": "active",
                "raw": {
                    "MockPatNum": "mock-patient-1003",
                    "FName": "David",
                    "LName": "Chen",
                    "WirelessPhone": "7785550199",
                },
            },
        ]

        return patients[:limit]

    async def get_patient(self, external_patient_id: str) -> dict[str, Any] | None:
        patients = await self.list_patients(limit=100)

        for patient in patients:
            if patient["id"] == external_patient_id:
                return patient

        return None

    async def list_providers(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "mock-provider-2001",
                "full_name": "Dr. Sarah Valizadeh",
                "display_name": "Dr. Sarah",
                "title": "Dentist",
                "specialty": "General Dentistry",
                "is_active": True,
                "raw": {
                    "ProvNum": "mock-provider-2001",
                    "FName": "Sarah",
                    "LName": "Valizadeh",
                    "Abbr": "Dr. Sarah",
                },
            },
            {
                "id": "mock-provider-2002",
                "full_name": "Dr. Tara Zarrabian",
                "display_name": "Dr. Tara",
                "title": "Dentist",
                "specialty": "Emergency Dentistry",
                "is_active": True,
                "raw": {
                    "ProvNum": "mock-provider-2002",
                    "FName": "Tara",
                    "LName": "Zarrabian",
                    "Abbr": "Dr. Tara",
                },
            },
        ]

    async def list_appointments(
        self,
        date_start: str | None = None,
        date_end: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        base_day = self.today

        if date_start:
            try:
                base_day = datetime.fromisoformat(date_start).date()
            except Exception:
                base_day = self.today

        appointments = [
            {
                "id": "mock-appointment-3001",
                "patient_external_id": "mock-patient-1001",
                "provider_external_id": "mock-provider-2001",
                "starts_at": datetime(
                    base_day.year,
                    base_day.month,
                    base_day.day,
                    9,
                    0,
                    tzinfo=timezone.utc,
                ).isoformat(),
                "ends_at": datetime(
                    base_day.year,
                    base_day.month,
                    base_day.day,
                    10,
                    0,
                    tzinfo=timezone.utc,
                ).isoformat(),
                "status": "confirmed",
                "reason": "Cleaning",
                "notes": "Mock appointment from PMS",
                "raw": {
                    "AptNum": "mock-appointment-3001",
                    "AptDateTime": f"{base_day.isoformat()} 09:00:00",
                    "Pattern": "XXXXXXXXXXXX",
                },
            },
            {
                "id": "mock-appointment-3002",
                "patient_external_id": "mock-patient-1002",
                "provider_external_id": "mock-provider-2002",
                "starts_at": datetime(
                    base_day.year,
                    base_day.month,
                    base_day.day,
                    11,
                    0,
                    tzinfo=timezone.utc,
                ).isoformat(),
                "ends_at": datetime(
                    base_day.year,
                    base_day.month,
                    base_day.day,
                    11,
                    30,
                    tzinfo=timezone.utc,
                ).isoformat(),
                "status": "confirmed",
                "reason": "Tooth pain",
                "notes": "Mock urgent appointment",
                "raw": {
                    "AptNum": "mock-appointment-3002",
                    "AptDateTime": f"{base_day.isoformat()} 11:00:00",
                    "Pattern": "XXXXXX",
                },
            },
            {
                "id": "mock-appointment-3003",
                "patient_external_id": "mock-patient-1003",
                "provider_external_id": "mock-provider-2001",
                "starts_at": datetime(
                    base_day.year,
                    base_day.month,
                    base_day.day,
                    14,
                    0,
                    tzinfo=timezone.utc,
                ).isoformat(),
                "ends_at": datetime(
                    base_day.year,
                    base_day.month,
                    base_day.day,
                    15,
                    0,
                    tzinfo=timezone.utc,
                ).isoformat(),
                "status": "confirmed",
                "reason": "New patient exam",
                "notes": "Mock new patient exam",
                "raw": {
                    "AptNum": "mock-appointment-3003",
                    "AptDateTime": f"{base_day.isoformat()} 14:00:00",
                    "Pattern": "XXXXXXXXXXXX",
                },
            },
        ]

        if date_end:
            try:
                end_day = datetime.fromisoformat(date_end).date()
                appointments = [
                    appt
                    for appt in appointments
                    if base_day <= datetime.fromisoformat(appt["starts_at"]).date() <= end_day
                ]
            except Exception:
                pass

        return appointments[:limit]