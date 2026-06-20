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

def normalize_search_text(text: str | None) -> str:
    if not text:
        return ""

    normalized = text.lower().strip()

    # Arabic/Persian character normalization
    replacements = {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "آ": "ا",
        "\u200c": " ",  # zero-width non-joiner
        "\u200f": "",
        "\u200e": "",
    }

    for old, new in replacements.items():
        normalized = normalized.replace(old, new)

    # Remove Arabic diacritics
    diacritics = [
        "\u064b", "\u064c", "\u064d", "\u064e", "\u064f",
        "\u0650", "\u0651", "\u0652", "\u0670"
    ]
    for mark in diacritics:
        normalized = normalized.replace(mark, "")

    # Normalize spacing
    normalized = " ".join(normalized.split())

    return normalized

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
    

def match_service_from_transcript(clinic_id: str | None, transcript: str):
    if not supabase or not clinic_id:
        print("Cannot match service: missing supabase or clinic_id")
        return None

    try:
        result = (
            supabase.table("service_keywords")
            .select(
                "keyword, language, match_type, "
                "service_categories(id, name, canonical_reason, default_urgency, creates_appointment_request)"
            )
            .eq("clinic_id", clinic_id)
            .eq("is_active", True)
            .execute()
        )

        transcript_lower = normalize_search_text(transcript)

        best_match = None
        best_keyword_length = 0

        for row in result.data or []:
            keyword = (row.get("keyword") or "").strip()
            if not keyword:
                continue

            keyword_lower = normalize_search_text(keyword)
            match_type = row.get("match_type") or "contains"

            matched = False

            if match_type == "contains":
                matched = keyword_lower in transcript_lower
            elif match_type == "exact":
                matched = keyword_lower == transcript_lower

            # Prefer longer/more specific keyword matches
            if matched and len(keyword_lower) > best_keyword_length:
                best_match = row
                best_keyword_length = len(keyword_lower)

        if not best_match:
            print("No service keyword matched transcript")
            return None

        category = best_match.get("service_categories") or {}

        matched_service = {
            "keyword": best_match.get("keyword"),
            "category_id": category.get("id"),
            "category_name": category.get("name"),
            "canonical_reason": category.get("canonical_reason"),
            "default_urgency": category.get("default_urgency") or "normal",
            "creates_appointment_request": bool(category.get("creates_appointment_request")),
        }

        print(f"Matched service from DB: {matched_service}")
        return matched_service

    except Exception as e:
        print(f"Error matching service from transcript: {e}")
        return None
    
