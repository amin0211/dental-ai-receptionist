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
    doctor_id: str | None = None,
    preferred_doctor_name: str | None = None,
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
            "doctor_id": doctor_id,
            "preferred_doctor_name": preferred_doctor_name,
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
    
def save_call_extraction(
    clinic_id: str | None,
    call_id: str | None,
    raw_transcript: str | None = None,
    cleaned_transcript: str | None = None,
    detected_language: str | None = None,
    patient_name: str | None = None,
    service_category: str | None = None,
    canonical_reason: str | None = None,
    preferred_time_raw: str | None = None,
    preferred_datetime: str | None = None,
    urgency: str | None = "normal",
    confidence: float | None = None,
    extraction_notes: str | None = None,
    preferred_date_raw: str | None = None,
    preferred_date_confirmed: bool | None = None,
    preferred_time_confirmed: bool | None = None,
    doctor_id: str | None = None,
    preferred_doctor_name: str | None = None,
):
    if not supabase:
        print("Supabase client is not initialized")
        return None

    try:
        payload = {
            "clinic_id": clinic_id,
            "call_id": call_id,
            "raw_transcript": raw_transcript,
            "cleaned_transcript": cleaned_transcript,
            "detected_language": detected_language,
            "patient_name": patient_name,
            "service_category": service_category,
            "canonical_reason": canonical_reason,
            "preferred_time_raw": preferred_time_raw,
            "preferred_datetime": preferred_datetime,
            "urgency": urgency or "normal",
            "confidence": confidence,
            "extraction_notes": extraction_notes,
            "preferred_date_raw": preferred_date_raw,
            "preferred_date_confirmed": preferred_date_confirmed,
            "preferred_time_confirmed": preferred_time_confirmed,
            "doctor_id": doctor_id,
            "preferred_doctor_name": preferred_doctor_name,
        }

        print(f"Inserting call extraction payload: {payload}")

        result = supabase.table("call_extractions").insert(payload).execute()

        print(f"Call extraction insert result: {result.data}")

        if result.data:
            return result.data[0]

        return None

    except Exception as e:
        print(f"Error saving call extraction: {e}")
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
    
def get_active_doctors_for_clinic(clinic_id: str | None) -> list[dict]:
    if not supabase or not clinic_id:
        print("Cannot load doctors: missing supabase or clinic_id")
        return []

    try:
        result = (
            supabase.table("clinic_doctors")
            .select("id, full_name, display_name, title, specialty, is_active")
            .eq("clinic_id", clinic_id)
            .eq("is_active", True)
            .order("full_name")
            .execute()
        )

        doctors = result.data or []
        print(f"Loaded active doctors for clinic {clinic_id}: {doctors}")
        return doctors

    except Exception as e:
        print(f"Error loading active doctors: {e}")
        return []


def match_doctor_from_name(
    doctors: list[dict],
    preferred_doctor_name: str | None,
) -> dict | None:
    if not doctors or not preferred_doctor_name:
        return None

    wanted = normalize_search_text(preferred_doctor_name)

    no_preference_values = [
        "no preference",
        "any doctor",
        "any dentist",
        "whoever is available",
        "does not matter",
        "فرقی ندارد",
        "فرقی نمیکند",
        "هر دکتری",
        "هرکسی",
        "مهم نیست",
    ]

    if wanted in [normalize_search_text(value) for value in no_preference_values]:
        return None

    best_match = None
    best_score = 0

    for doctor in doctors:
        full_name = normalize_search_text(doctor.get("full_name"))
        display_name = normalize_search_text(doctor.get("display_name"))
        specialty = normalize_search_text(doctor.get("specialty"))

        possible_names = [
            full_name,
            display_name,
            full_name.replace("dr.", "").replace("doctor", "").strip(),
            display_name.replace("dr.", "").replace("doctor", "").strip(),
        ]

        score = 0

        for name in possible_names:
            if not name:
                continue

            if wanted == name:
                score = max(score, 100)

            elif wanted in name:
                score = max(score, 80)

            elif name in wanted:
                score = max(score, 75)

            # Match last name, like caller says "Lee" or "Dr. Lee"
            name_parts = [part for part in name.split() if len(part) >= 3]
            for part in name_parts:
                if part in wanted:
                    score = max(score, 60)

        if specialty and specialty in wanted:
            score = max(score, 40)

        if score > best_score:
            best_score = score
            best_match = doctor

    if best_score >= 60:
        print(f"Matched doctor: {best_match} with score {best_score}")
        return best_match

    print(f"No doctor matched preferred_doctor_name={preferred_doctor_name}")
    return None