import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    return phone.strip()


def find_clinic_by_twilio_number(to_number: str | None):
    if not supabase:
        print("Supabase client is not initialized")
        return None

    clean_number = normalize_phone(to_number)

    try:
        print(f"Looking up clinic for To number: {clean_number}")

        result = (
            supabase.table("clinics")
            .select("*")
            .eq("phone_number", clean_number)
            .limit(1)
            .execute()
        )

        print(f"Clinic lookup result: {result.data}")

        if result.data:
            return result.data[0]

        return None

    except Exception as e:
        print(f"Error finding clinic: {e}")
        return None


def save_call_to_db(
    clinic_id: str | None,
    twilio_call_sid: str | None,
    caller_phone: str | None,
    speech_result: str | None = "",
    confidence: str | None = None,
    intent: str | None = "general",
    urgency: str | None = "normal",
    summary: str | None = "",
):
    if not supabase:
        print("Supabase client is not initialized")
        return None

    try:
        payload = {
            "clinic_id": clinic_id,
            "twilio_call_sid": twilio_call_sid,
            "caller_phone": normalize_phone(caller_phone),
            "speech_result": speech_result or "",
            "confidence": confidence,
            "intent": intent or "general",
            "urgency": urgency or "normal",
            "summary": summary or "",
        }

        print(f"Inserting call payload: {payload}")

        result = supabase.table("calls").insert(payload).execute()

        print(f"Call insert result: {result.data}")

        if result.data:
            return result.data[0]

        return None

    except Exception as e:
        print(f"Error saving call to database: {e}")
        return None


def create_appointment_request(
    clinic_id: str | None,
    call_id: str | None,
    patient_phone: str | None,
    reason: str | None,
    urgency: str | None = "normal",
    patient_name: str | None = None,
    preferred_time: str | None = None,
    status: str = "new",
):
    if not supabase:
        print("Supabase client is not initialized")
        return None

    try:
        payload = {
            "clinic_id": clinic_id,
            "call_id": call_id,
            "patient_phone": normalize_phone(patient_phone),
            "patient_name": patient_name,
            "reason": reason or "",
            "preferred_time": preferred_time,
            "urgency": urgency or "normal",
            "status": status,
        }

        print(f"Inserting appointment request payload: {payload}")

        result = supabase.table("appointment_requests").insert(payload).execute()

        print(f"Appointment request insert result: {result.data}")

        if result.data:
            return result.data[0]

        return None

    except Exception as e:
        print(f"Error creating appointment request: {e}")
        return None


def update_appointment_request(appointment_id: str, updates: dict):
    if not supabase:
        print("Supabase client is not initialized")
        return None

    try:
        print(f"Updating appointment request {appointment_id}: {updates}")

        result = (
            supabase.table("appointment_requests")
            .update(updates)
            .eq("id", appointment_id)
            .execute()
        )

        print(f"Appointment update result: {result.data}")

        if result.data:
            return result.data[0]

        return None

    except Exception as e:
        print(f"Error updating appointment request: {e}")
        return None
    
def update_call(call_id: str, updates: dict):
    if not supabase:
        print("Supabase client is not initialized")
        return None

    try:
        print(f"Updating call {call_id}: {updates}")

        result = (
            supabase.table("calls")
            .update(updates)
            .eq("id", call_id)
            .execute()
        )

        print(f"Call update result: {result.data}")

        if result.data:
            return result.data[0]

        return None

    except Exception as e:
        print(f"Error updating call: {e}")
        return None