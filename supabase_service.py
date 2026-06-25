import os
from supabase import create_client, Client
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    return phone.strip()




def normalize_phone_digits(phone: str | None) -> str:
    if not phone:
        return ""

    return "".join(ch for ch in str(phone) if ch.isdigit())


def phones_match(phone_a: str | None, phone_b: str | None) -> bool:
    digits_a = normalize_phone_digits(phone_a)
    digits_b = normalize_phone_digits(phone_b)

    if not digits_a or not digits_b:
        return False

    if digits_a == digits_b:
        return True

    # Canada/US case:
    # +17788816242 vs 7788816242
    if len(digits_a) == 11 and digits_a.startswith("1"):
        digits_a_without_country = digits_a[1:]
    else:
        digits_a_without_country = digits_a

    if len(digits_b) == 11 and digits_b.startswith("1"):
        digits_b_without_country = digits_b[1:]
    else:
        digits_b_without_country = digits_b

    return digits_a_without_country == digits_b_without_country


def find_patients_by_phone(
    clinic_id: str | None,
    phone: str | None,
) -> list[dict]:
    if not supabase or not clinic_id or not phone:
        print(
            f"Cannot find patients by phone: supabase={bool(supabase)}, clinic_id={clinic_id}, phone={phone}"
        )
        return []

    clean_phone = normalize_phone(phone)
    search_digits = normalize_phone_digits(clean_phone)

    try:
        print(
            f"Finding patients by phone | clinic_id={clinic_id} | raw_phone={phone} | clean_phone={clean_phone} | digits={search_digits}"
        )

        # For MVP, load clinic patients and compare normalized digits in Python.
        # This avoids exact-match problems with +1, spaces, dashes, parentheses, etc.
        result = (
            supabase.table("patients")
            .select(
                """
                id,
                clinic_id,
                full_name,
                phone_primary,
                phone_secondary,
                email,
                date_of_birth,
                notes
                """
            )
            .eq("clinic_id", clinic_id)
            .execute()
        )

        all_patients = result.data or []

        matched_patients = []

        for patient in all_patients:
            phone_primary = patient.get("phone_primary")
            phone_secondary = patient.get("phone_secondary")

            if phones_match(clean_phone, phone_primary) or phones_match(
                clean_phone, phone_secondary
            ):
                matched_patients.append(patient)

        print(
            f"Patient phone lookup result | searched={clean_phone} | digits={search_digits} | matched={matched_patients}"
        )

        return matched_patients

    except Exception as e:
        print(f"Error finding patients by phone: {e}")
        return []
     
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
            .eq("twilio_phone_number", clean_number)
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
    patient_id: str | None = None,
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
            "patient_id": patient_id,
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
    patient_id: str | None = None,
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
            "patient_id": patient_id,
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
        keyword_result = (
            supabase.table("service_keywords")
            .select(
                """
                id,
                category_id,
                keyword,
                language,
                match_type,
                service_categories (
                    id,
                    name,
                    canonical_reason,
                    default_urgency,
                    creates_appointment_request,
                    default_duration_minutes,
                    is_active
                )
                """
            )
            .eq("clinic_id", clinic_id)
            .eq("is_active", True)
            .execute()
        )

        transcript_normalized = normalize_search_text(transcript)

        if not transcript_normalized:
            print("No transcript text to match service")
            return None

        generic_keywords = {
            "appointment",
            "book appointment",
            "schedule appointment",
            "dental appointment",
            "tooth problem",
            "dental problem",
            "problem",
            "issue",
            "concern",
            "dentist",
            "dental visit",
            "visit",
        }

        generic_canonical_reasons = {
            "general",
            "general_appointment",
            "appointment",
            "dental_appointment",
        }

        best_candidate = None

        for row in keyword_result.data or []:
            keyword = (row.get("keyword") or "").strip()
            category_id = row.get("category_id")
            category = row.get("service_categories") or {}

            if not keyword or not category_id:
                continue

            if category.get("is_active") is False:
                continue

            keyword_normalized = normalize_search_text(keyword)
            match_type = row.get("match_type") or "contains"

            if not keyword_normalized:
                continue

            matched = False

            if match_type == "contains":
                matched = keyword_normalized in transcript_normalized

            elif match_type == "exact":
                matched = keyword_normalized == transcript_normalized

            else:
                matched = keyword_normalized in transcript_normalized

            if not matched:
                continue

            canonical_reason = normalize_search_text(category.get("canonical_reason"))
            category_name = normalize_search_text(category.get("name"))

            # Base score
            score = 0

            # Exact match is stronger than contains
            if keyword_normalized == transcript_normalized:
                score += 1000
            else:
                score += 500

            # More specific multi-word treatment keywords should beat generic words
            score += len(keyword_normalized)

            if len(keyword_normalized.split()) >= 2:
                score += 100

            # Strong penalty for generic categories/keywords
            if keyword_normalized in generic_keywords:
                score -= 300

            if canonical_reason in generic_canonical_reasons:
                score -= 500

            if "general" in category_name:
                score -= 500

            candidate = {
                "score": score,
                "row": row,
                "category": category,
                "keyword_normalized": keyword_normalized,
            }

            if best_candidate is None or candidate["score"] > best_candidate["score"]:
                best_candidate = candidate

        if not best_candidate:
            print("No service keyword matched transcript")
            return None

        best_match = best_candidate["row"]
        category = best_candidate["category"]

        matched_service = {
            "keyword": best_match.get("keyword"),
            "category_id": category.get("id"),
            "category_name": category.get("name"),
            "canonical_reason": category.get("canonical_reason"),
            "default_urgency": category.get("default_urgency") or "normal",
            "creates_appointment_request": bool(category.get("creates_appointment_request")),
            "duration_minutes": category.get("default_duration_minutes") or 30,
            "match_score": best_candidate["score"],
        }

        print(f"Matched service from DB: {matched_service}")
        return matched_service

    except Exception as e:
        print(f"Error matching service from transcript: {e}")
        return None


def parse_db_time(value) -> time | None:
    if not value:
        return None

    if isinstance(value, time):
        return value

    value = str(value)

    try:
        return time.fromisoformat(value)
    except Exception:
        pass

    try:
        return datetime.strptime(value, "%H:%M:%S").time()
    except Exception:
        pass

    try:
        return datetime.strptime(value, "%H:%M").time()
    except Exception:
        return None


def combine_local_datetime(
    target_date: date,
    target_time: time,
    timezone_name: str = "America/Vancouver",
) -> datetime:
    tz = ZoneInfo(timezone_name)

    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        target_time.hour,
        target_time.minute,
        target_time.second,
        tzinfo=tz,
    )


def python_day_to_db_day(target_date: date) -> int:
    # Python: Monday=0 ... Sunday=6
    # DB: Sunday=0, Monday=1 ... Saturday=6
    return (target_date.weekday() + 1) % 7


def iso_datetime_for_supabase(value: datetime) -> str:
    return value.isoformat()
    
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

def get_calendar_availability_rules_for_doctor(
    clinic_id: str | None,
    doctor_id: str | None,
    start_date: date,
    end_date: date,
) -> list[dict]:
    if not supabase or not clinic_id or not doctor_id:
        print("Cannot load availability rules: missing supabase, clinic_id, or doctor_id")
        return []

    try:
        result = (
            supabase.table("calendar_availability_rules")
            .select("*")
            .eq("clinic_id", clinic_id)
            .eq("doctor_id", doctor_id)
            .eq("is_active", True)
            .lte("start_date", end_date.isoformat())
            .or_(f"end_date.is.null,end_date.gte.{start_date.isoformat()}")
            .order("start_date")
            .order("start_time")
            .execute()
        )

        rows = result.data or []

        print(
            f"Loaded availability rules for doctor={doctor_id}, "
            f"range={start_date} to {end_date}: {rows}"
        )

        return rows

    except Exception as e:
        print(f"Error loading availability rules: {e}")
        return []


def get_calendar_availability_exceptions_for_rules(
    clinic_id: str | None,
    rule_ids: list[str],
    start_date: date,
    end_date: date,
) -> list[dict]:
    if not supabase or not clinic_id or not rule_ids:
        return []

    try:
        result = (
            supabase.table("calendar_availability_exceptions")
            .select("*")
            .eq("clinic_id", clinic_id)
            .in_("rule_id", rule_ids)
            .gte("exception_date", start_date.isoformat())
            .lte("exception_date", end_date.isoformat())
            .execute()
        )

        rows = result.data or []

        print(
            f"Loaded availability exceptions for rules={rule_ids}, "
            f"range={start_date} to {end_date}: {rows}"
        )

        return rows

    except Exception as e:
        print(f"Error loading availability exceptions: {e}")
        return []


def rule_applies_to_date(rule: dict, target_date: date) -> bool:
    start_date_raw = rule.get("start_date")
    end_date_raw = rule.get("end_date")

    if not start_date_raw:
        return False

    rule_start = date.fromisoformat(str(start_date_raw))

    if target_date < rule_start:
        return False

    if end_date_raw:
        rule_end = date.fromisoformat(str(end_date_raw))
        if target_date > rule_end:
            return False

    repeat_type = rule.get("repeat_type") or "none"
    db_day = python_day_to_db_day(target_date)

    if repeat_type == "none":
        return target_date == rule_start

    if repeat_type == "daily":
        return True

    if repeat_type == "weekdays":
        return target_date.weekday() <= 4

    if repeat_type in ["weekly", "custom"]:
        return rule.get("day_of_week") == db_day

    return False


def get_daily_available_intervals_from_rules(
    rules: list[dict],
    exceptions: list[dict],
    target_date: date,
    timezone_name: str = "America/Vancouver",
) -> list[tuple[datetime, datetime]]:
    intervals = []

    exception_by_rule_id: dict[str, dict] = {}

    for exception in exceptions:
        if str(exception.get("exception_date")) != target_date.isoformat():
            continue

        rule_id = exception.get("rule_id")
        if rule_id:
            exception_by_rule_id[rule_id] = exception

    for rule in rules:
        if not rule_applies_to_date(rule, target_date):
            continue

        rule_id = rule.get("id")
        exception = exception_by_rule_id.get(rule_id)

        if exception and exception.get("exception_type") == "cancelled":
            continue

        if exception and exception.get("exception_type") == "modified":
            start_time = parse_db_time(exception.get("start_time"))
            end_time = parse_db_time(exception.get("end_time"))
        else:
            start_time = parse_db_time(rule.get("start_time"))
            end_time = parse_db_time(rule.get("end_time"))

        if not start_time or not end_time:
            continue

        start_dt = combine_local_datetime(target_date, start_time, timezone_name)
        end_dt = combine_local_datetime(target_date, end_time, timezone_name)

        if start_dt < end_dt:
            intervals.append((start_dt, end_dt))

    return intervals


def get_doctor_busy_appointments(
    clinic_id: str | None,
    doctor_id: str | None,
    start_dt: datetime,
    end_dt: datetime,
) -> list[dict]:
    if not supabase or not clinic_id or not doctor_id:
        print("Cannot load busy appointments: missing supabase, clinic_id, or doctor_id")
        return []

    try:
        result = (
            supabase.table("appointments")
            .select("id, clinic_id, doctor_id, start_time, end_time, status")
            .eq("clinic_id", clinic_id)
            .eq("doctor_id", doctor_id)
            .in_("status", ["confirmed"])
            .lt("start_time", iso_datetime_for_supabase(end_dt))
            .gt("end_time", iso_datetime_for_supabase(start_dt))
            .order("start_time")
            .execute()
        )

        rows = result.data or []

        print(
            f"Loaded busy appointments for doctor={doctor_id}, "
            f"range={start_dt} to {end_dt}: {rows}"
        )

        return rows

    except Exception as e:
        print(f"Error loading busy appointments: {e}")
        return []



def subtract_busy_intervals(
    available_intervals: list[tuple[datetime, datetime]],
    busy_intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    free_intervals = available_intervals[:]

    for busy_start, busy_end in busy_intervals:
        next_free = []

        for free_start, free_end in free_intervals:
            # No overlap
            if busy_end <= free_start or busy_start >= free_end:
                next_free.append((free_start, free_end))
                continue

            # Left remaining part
            if busy_start > free_start:
                next_free.append((free_start, busy_start))

            # Right remaining part
            if busy_end < free_end:
                next_free.append((busy_end, free_end))

        free_intervals = next_free

    return [
        (start, end)
        for start, end in free_intervals
        if start < end
    ]

def split_intervals_into_slots(
    free_intervals: list[tuple[datetime, datetime]],
    duration_minutes: int,
    step_minutes: int = 15,
) -> list[tuple[datetime, datetime]]:
    slots = []

    duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=step_minutes)

    for free_start, free_end in free_intervals:
        cursor = free_start

        while cursor + duration <= free_end:
            slots.append((cursor, cursor + duration))
            cursor += step

    return slots

def find_next_available_slots_for_doctor(
    clinic_id: str | None,
    doctor_id: str | None,
    duration_minutes: int = 30,
    timezone_name: str = "America/Vancouver",
    start_date: date | None = None,
    days_ahead: int = 60,
    max_slots: int = 2,
    step_minutes: int = 15,
) -> list[dict]:
    if not clinic_id or not doctor_id:
        print("Cannot find slots: missing clinic_id or doctor_id")
        return []

    if duration_minutes <= 0:
        duration_minutes = 30

    tz = ZoneInfo(timezone_name)

    today = datetime.now(tz).date()
    search_start_date = start_date or today
    search_end_date = search_start_date + timedelta(days=days_ahead)

    search_start_dt = datetime.combine(
        search_start_date,
        time(0, 0),
        tzinfo=tz,
    )

    search_end_dt = datetime.combine(
        search_end_date,
        time(23, 59),
        tzinfo=tz,
    )

    rules = get_calendar_availability_rules_for_doctor(
        clinic_id=clinic_id,
        doctor_id=doctor_id,
        start_date=search_start_date,
        end_date=search_end_date,
    )

    if not rules:
        print(f"No availability rules found for doctor={doctor_id}")
        return []

    exceptions = get_calendar_availability_exceptions_for_rules(
        clinic_id=clinic_id,
        rule_ids=[
            row.get("id")
            for row in rules
            if row.get("id")
        ],
        start_date=search_start_date,
        end_date=search_end_date,
    )

    busy_appointments = get_doctor_busy_appointments(
        clinic_id=clinic_id,
        doctor_id=doctor_id,
        start_dt=search_start_dt,
        end_dt=search_end_dt,
    )

    found_slots = []

    current_date = search_start_date

    while current_date <= search_end_date and len(found_slots) < max_slots:
        available_intervals = get_daily_available_intervals_from_rules(
            rules=rules,
            exceptions=exceptions,
            target_date=current_date,
            timezone_name=timezone_name,
        )

        if not available_intervals:
            current_date += timedelta(days=1)
            continue

        day_start = datetime.combine(current_date, time(0, 0), tzinfo=tz)
        day_end = datetime.combine(current_date, time(23, 59), tzinfo=tz)

        busy_intervals = []

        for appointment in busy_appointments:
            try:
                appointment_start = datetime.fromisoformat(
                    str(appointment.get("start_time")).replace("Z", "+00:00")
                ).astimezone(tz)

                appointment_end = datetime.fromisoformat(
                    str(appointment.get("end_time")).replace("Z", "+00:00")
                ).astimezone(tz)
            except Exception:
                continue

            if appointment_end <= day_start or appointment_start >= day_end:
                continue

            busy_intervals.append((appointment_start, appointment_end))

        free_intervals = subtract_busy_intervals(
            available_intervals=available_intervals,
            busy_intervals=busy_intervals,
        )

        day_slots = split_intervals_into_slots(
            free_intervals=free_intervals,
            duration_minutes=duration_minutes,
            step_minutes=step_minutes,
        )

        now_dt = datetime.now(tz)

        for slot_start, slot_end in day_slots:
            if slot_start <= now_dt:
                continue

            found_slots.append(
                {
                    "doctor_id": doctor_id,
                    "clinic_id": clinic_id,
                    "starts_at": slot_start.isoformat(),
                    "ends_at": slot_end.isoformat(),
                    "date": slot_start.date().isoformat(),
                    "start_time": slot_start.strftime("%H:%M"),
                    "end_time": slot_end.strftime("%H:%M"),
                    "duration_minutes": duration_minutes,
                    "timezone": timezone_name,
                    "display": format_slot_for_ai(slot_start, slot_end),
                }
            )

            if len(found_slots) >= max_slots:
                break

        current_date += timedelta(days=1)

    print(
        f"Found available slots for doctor={doctor_id}, "
        f"duration={duration_minutes}: {found_slots}"
    )

    return found_slots

def format_time_for_ai(value: datetime) -> str:
    # 11:00 AM -> 11 AM
    # 11:30 AM -> 11:30 AM
    if value.minute == 0:
        return value.strftime("%I %p").lstrip("0")

    return value.strftime("%I:%M %p").lstrip("0")


def format_slot_for_ai(slot_start: datetime, slot_end: datetime) -> str:
    day_name = slot_start.strftime("%A")
    month_name = slot_start.strftime("%B")
    day_number = slot_start.day

    start_display = format_time_for_ai(slot_start)

    return f"{day_name}, {month_name} {day_number} at {start_display}"



def parse_preferred_date_raw(
    preferred_date_raw: str | None,
    timezone_name: str = "America/Vancouver",
) -> date | None:
    if not preferred_date_raw:
        return None

    text = str(preferred_date_raw).strip()
    if not text:
        return None

    tz = ZoneInfo(timezone_name)
    today = datetime.now(tz).date()

    # ISO format: 2026-07-20
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        pass

    formats = [
        "%B %d %Y",   # July 20 2026
        "%b %d %Y",   # Jul 20 2026
        "%d %B %Y",   # 20 July 2026
        "%d %b %Y",   # 20 Jul 2026
        "%B %d",      # July 20
        "%b %d",      # Jul 20
        "%d %B",      # 20 July
        "%d %b",      # 20 Jul
        "%m/%d/%Y",
        "%m/%d",
        "%m-%d-%Y",
        "%m-%d",
    ]

    for fmt in formats:
        try:
            parsed_dt = datetime.strptime(text, fmt)

            # If year is not included, choose the next future occurrence.
            if "%Y" not in fmt:
                candidate = date(today.year, parsed_dt.month, parsed_dt.day)

                if candidate < today:
                    candidate = date(today.year + 1, parsed_dt.month, parsed_dt.day)

                return candidate

            return parsed_dt.date()

        except Exception:
            continue

    normalized = normalize_search_text(text)

    if normalized in ["today", "امروز"]:
        return today

    if normalized in ["tomorrow", "فردا"]:
        return today + timedelta(days=1)

    if "next week" in normalized or "هفته بعد" in normalized:
        return today + timedelta(days=7)

    if (
        "next month" in normalized
        or "ماه بعد" in normalized
        or "یک ماه دیگه" in normalized
        or "یک ماه دیگر" in normalized
    ):
        return today + timedelta(days=30)

    print(f"Could not parse preferred_date_raw: {preferred_date_raw}")
    return None


def get_service_category_doctor_ids(
    clinic_id: str | None,
    service_category_id: str | None,
) -> list[str]:
    if not supabase or not clinic_id or not service_category_id:
        print("Cannot load service doctors: missing supabase, clinic_id, or service_category_id")
        return []

    try:
        result = (
            supabase.table("clinic_doctor_services")
            .select("doctor_id")
            .eq("clinic_id", clinic_id)
            .eq("service_category_id", service_category_id)
            .eq("is_active", True)
            .execute()
        )

        doctor_ids = [
            row.get("doctor_id")
            for row in result.data or []
            if row.get("doctor_id")
        ]

        print(
            f"Loaded doctor ids for service_category_id={service_category_id}: "
            f"{doctor_ids}"
        )

        return doctor_ids

    except Exception as e:
        print(f"Error loading service doctors: {e}")
        return []




def get_doctor_display_name(doctor: dict | None) -> str | None:
    if not doctor:
        return None

    return (
        doctor.get("display_name")
        or doctor.get("full_name")
        or doctor.get("name")
    )


def attach_doctor_name_to_slots(
    slots: list[dict],
    doctor: dict,
) -> list[dict]:
    doctor_name = get_doctor_display_name(doctor)

    enriched_slots = []

    for slot in slots:
        slot_copy = dict(slot)

        # Internal only. Do not add doctor name to display.
        slot_copy["doctor_name"] = doctor_name

        enriched_slots.append(slot_copy)

    return enriched_slots

def get_upcoming_appointments_for_ai(
    clinic_id: str | None,
    patient_id: str | None,
    timezone_name: str = "America/Vancouver",
) -> dict:
    if not supabase:
        return {
            "ok": False,
            "reason": "supabase_not_initialized",
            "message_for_ai": "Tell the caller the front desk can help verify the appointment.",
            "appointments": [],
        }

    if not clinic_id:
        return {
            "ok": False,
            "reason": "missing_clinic_id",
            "message_for_ai": "Tell the caller the front desk can help verify the appointment.",
            "appointments": [],
        }

    if not patient_id:
        return {
            "ok": False,
            "reason": "missing_patient_id",
            "message_for_ai": "Ask which patient this is for before checking appointments.",
            "appointments": [],
        }

    try:
        tz = ZoneInfo(timezone_name)
        now_iso = datetime.now(tz).isoformat()

        result = (
            supabase.table("appointments")
            .select(
                """
                id,
                clinic_id,
                patient_id,
                doctor_id,
                service_category_id,
                service_name,
                reason,
                urgency,
                start_time,
                end_time,
                duration_minutes,
                status,
                notes
                """
            )
            .eq("clinic_id", clinic_id)
            .eq("patient_id", patient_id)
            .gte("start_time", now_iso)
            .neq("status", "cancelled")
            .order("start_time")
            .limit(3)
            .execute()
        )

        appointments = result.data or []

        if not appointments:
            return {
                "ok": True,
                "status": "not_found",
                "message_for_ai": "Tell the caller you could not find an upcoming appointment and the front desk can help.",
                "appointments": [],
            }

        doctor_ids = [
            appointment.get("doctor_id")
            for appointment in appointments
            if appointment.get("doctor_id")
        ]

        doctors_by_id = {}

        if doctor_ids:
            doctor_result = (
                supabase.table("clinic_doctors")
                .select("id, full_name, display_name")
                .eq("clinic_id", clinic_id)
                .in_("id", doctor_ids)
                .execute()
            )

            for doctor in doctor_result.data or []:
                doctors_by_id[doctor.get("id")] = (
                    doctor.get("display_name")
                    or doctor.get("full_name")
                    or "the doctor"
                )

        formatted_appointments = []

        for appointment in appointments:
            start_raw = appointment.get("start_time")
            end_raw = appointment.get("end_time")

            try:
                start_dt = datetime.fromisoformat(
                    str(start_raw).replace("Z", "+00:00")
                ).astimezone(tz)
            except Exception:
                start_dt = None

            try:
                end_dt = datetime.fromisoformat(
                    str(end_raw).replace("Z", "+00:00")
                ).astimezone(tz)
            except Exception:
                end_dt = None

            doctor_name = doctors_by_id.get(
                appointment.get("doctor_id"),
                "the doctor",
            )

            display = None

            if start_dt:
                display = f"{doctor_name} on {format_slot_for_ai(start_dt, end_dt or start_dt)}"

            formatted_appointments.append(
                {
                    "id": appointment.get("id"),
                    "doctor_id": appointment.get("doctor_id"),
                    "doctor_name": doctor_name,
                    "service_name": appointment.get("service_name"),
                    "reason": appointment.get("reason"),
                    "status": appointment.get("status"),
                    "start_time": appointment.get("start_time"),
                    "end_time": appointment.get("end_time"),
                    "display": display,
                }
            )

        return {
            "ok": True,
            "status": "found",
            "message_for_ai": (
                "Tell the caller the earliest upcoming appointment. "
                "Say the doctor name, date, and start time only."
            ),
            "appointments": formatted_appointments,
        }

    except Exception as e:
        print(f"Error loading upcoming appointments for AI: {e}")

        return {
            "ok": False,
            "reason": "lookup_failed",
            "message_for_ai": "Tell the caller the front desk can help verify the appointment.",
            "appointments": [],
        }

def get_patient_appointment_by_id(
    clinic_id: str | None,
    patient_id: str | None,
    appointment_id: str | None,
) -> dict | None:
    if not supabase or not clinic_id or not patient_id or not appointment_id:
        return None

    try:
        result = (
            supabase.table("appointments")
            .select("*")
            .eq("clinic_id", clinic_id)
            .eq("patient_id", patient_id)
            .eq("id", appointment_id)
            .limit(1)
            .execute()
        )

        if result.data:
            return result.data[0]

        return None

    except Exception as e:
        print(f"Error loading patient appointment by id: {e}")
        return None


def cancel_appointment_for_ai(
    clinic_id: str | None,
    patient_id: str | None,
    appointment_id: str | None,
) -> dict:
    if not supabase:
        return {
            "ok": False,
            "reason": "supabase_not_initialized",
            "message_for_ai": "Tell the caller the front desk can help cancel the appointment.",
        }

    if not clinic_id or not patient_id or not appointment_id:
        return {
            "ok": False,
            "reason": "missing_required_fields",
            "message_for_ai": "Tell the caller the appointment could not be cancelled automatically and the front desk can help.",
        }

    appointment = get_patient_appointment_by_id(
        clinic_id=clinic_id,
        patient_id=patient_id,
        appointment_id=appointment_id,
    )

    if not appointment:
        return {
            "ok": False,
            "reason": "appointment_not_found",
            "message_for_ai": "Tell the caller you could not find that appointment and the front desk can help.",
        }

    if appointment.get("status") == "cancelled":
        return {
            "ok": True,
            "status": "already_cancelled",
            "message_for_ai": "Tell the caller this appointment was already cancelled.",
            "appointment": appointment,
        }

    try:
        result = (
            supabase.table("appointments")
            .update(
                {
                    "status": "cancelled",
                    "updated_at": datetime.now(
                        ZoneInfo("America/Vancouver")
                    ).isoformat(),
                }
            )
            .eq("clinic_id", clinic_id)
            .eq("patient_id", patient_id)
            .eq("id", appointment_id)
            .execute()
        )

        updated = result.data[0] if result.data else None

        return {
            "ok": True,
            "status": "cancelled",
            "message_for_ai": "Tell the caller the appointment has been cancelled.",
            "appointment": updated or appointment,
        }

    except Exception as e:
        print(f"Error cancelling appointment for AI: {e}")

        return {
            "ok": False,
            "reason": "cancel_failed",
            "message_for_ai": "Tell the caller the front desk can help cancel the appointment.",
        }


def appointment_slot_has_conflict(
    clinic_id: str | None,
    doctor_id: str | None,
    start_time_iso: str | None,
    end_time_iso: str | None,
    ignore_appointment_id: str | None = None,
) -> bool:
    if (
        not supabase
        or not clinic_id
        or not doctor_id
        or not start_time_iso
        or not end_time_iso
    ):
        return True

    try:
        query = (
            supabase.table("appointments")
            .select("id, start_time, end_time, status")
            .eq("clinic_id", clinic_id)
            .eq("doctor_id", doctor_id)
            .neq("status", "cancelled")
            .lt("start_time", end_time_iso)
            .gt("end_time", start_time_iso)
        )

        if ignore_appointment_id:
            query = query.neq("id", ignore_appointment_id)

        result = query.execute()

        return bool(result.data)

    except Exception as e:
        print(f"Error checking appointment slot conflict: {e}")
        return True

def reschedule_appointment_for_ai(
    clinic_id: str | None,
    patient_id: str | None,
    appointment_id: str | None,
    doctor_id: str | None,
    start_time_iso: str | None,
    end_time_iso: str | None,
    call_id: str | None = None,
    patient_phone: str | None = None,
) -> dict:
    if not supabase:
        return {
            "ok": False,
            "reason": "supabase_not_initialized",
            "message_for_ai": "Tell the caller the front desk can help reschedule the appointment.",
        }

    if (
        not clinic_id
        or not patient_id
        or not appointment_id
        or not doctor_id
        or not start_time_iso
        or not end_time_iso
    ):
        return {
            "ok": False,
            "reason": "missing_required_fields",
            "message_for_ai": "Tell the caller the appointment could not be changed automatically and the front desk can help.",
        }

    appointment = get_patient_appointment_by_id(
        clinic_id=clinic_id,
        patient_id=patient_id,
        appointment_id=appointment_id,
    )

    if not appointment:
        return {
            "ok": False,
            "reason": "appointment_not_found",
            "message_for_ai": "Tell the caller you could not find that appointment and the front desk can help.",
        }

    if appointment.get("status") == "cancelled":
        return {
            "ok": False,
            "reason": "appointment_already_cancelled",
            "message_for_ai": "Tell the caller this appointment is already cancelled and the front desk can help book a new one.",
        }

    has_conflict = appointment_slot_has_conflict(
        clinic_id=clinic_id,
        doctor_id=doctor_id,
        start_time_iso=start_time_iso,
        end_time_iso=end_time_iso,
        ignore_appointment_id=appointment_id,
    )

    if has_conflict:
        return {
            "ok": False,
            "reason": "slot_conflict",
            "message_for_ai": "Tell the caller that time is no longer available and offer to check another time.",
        }

    try:
        now_iso = datetime.now(ZoneInfo("America/Vancouver")).isoformat()

        # 1. Cancel the old appointment.
        cancel_result = (
            supabase.table("appointments")
            .update(
                {
                    "status": "cancelled",
                    "updated_at": now_iso,
                    "notes": (
                        (appointment.get("notes") or "")
                        + "\nRescheduled by AI receptionist. New appointment request created."
                    ).strip(),
                }
            )
            .eq("clinic_id", clinic_id)
            .eq("patient_id", patient_id)
            .eq("id", appointment_id)
            .execute()
        )

        cancelled_appointment = (
            cancel_result.data[0]
            if cancel_result.data
            else appointment
        )

        # 2. Load patient info if available.
        patient_name = appointment.get("patient_name")
        final_patient_phone = patient_phone or appointment.get("patient_phone")

        if not patient_name or not final_patient_phone:
            try:
                patient_result = (
                    supabase.table("patients")
                    .select("id, full_name, phone_primary")
                    .eq("clinic_id", clinic_id)
                    .eq("id", patient_id)
                    .limit(1)
                    .execute()
                )

                if patient_result.data:
                    patient_row = patient_result.data[0]
                    patient_name = patient_name or patient_row.get("full_name")
                    final_patient_phone = (
                        final_patient_phone
                        or patient_row.get("phone_primary")
                    )
            except Exception as patient_lookup_error:
                print(f"Could not load patient for reschedule request: {patient_lookup_error}")

        # 3. Load doctor name if available.
        preferred_doctor_name = appointment.get("preferred_doctor_name")

        try:
            doctor_result = (
                supabase.table("clinic_doctors")
                .select("id, full_name, display_name")
                .eq("clinic_id", clinic_id)
                .eq("id", doctor_id)
                .limit(1)
                .execute()
            )

            if doctor_result.data:
                doctor_row = doctor_result.data[0]
                preferred_doctor_name = (
                    doctor_row.get("display_name")
                    or doctor_row.get("full_name")
                    or preferred_doctor_name
                )
        except Exception as doctor_lookup_error:
            print(f"Could not load doctor for reschedule request: {doctor_lookup_error}")

        # 4. Format preferred date/time from selected new slot.
        preferred_date_raw = None
        preferred_time_raw = None
        preferred_time_combined = start_time_iso

        try:
            tz = ZoneInfo("America/Vancouver")

            selected_start = datetime.fromisoformat(
                str(start_time_iso).replace("Z", "+00:00")
            ).astimezone(tz)

            preferred_date_raw = selected_start.date().isoformat()
            preferred_time_raw = selected_start.strftime("%H:%M")
            preferred_time_combined = (
                f"{preferred_date_raw} {preferred_time_raw}"
            )
        except Exception as parse_error:
            print(f"Could not parse selected reschedule slot: {parse_error}")

        # 5. Create a new appointment_request, like a fresh booking request.
        request_payload = {
            "clinic_id": clinic_id,
            "call_id": call_id,
            "patient_id": patient_id,
            "patient_phone": normalize_phone(final_patient_phone),
            "patient_name": patient_name,
            "reason": appointment.get("reason") or appointment.get("service_name") or "reschedule",
            "preferred_time": preferred_time_combined,
            "urgency": appointment.get("urgency") or "normal",
            "status": "new",
            "doctor_id": doctor_id,
            "preferred_doctor_name": preferred_doctor_name,
        }

        print(f"Inserting reschedule appointment request payload: {request_payload}")

        request_result = (
            supabase.table("appointment_requests")
            .insert(request_payload)
            .execute()
        )

        new_request = request_result.data[0] if request_result.data else None

        if new_request and new_request.get("id"):
            request_updates = {
                "doctor_id": doctor_id,
                "preferred_doctor_name": preferred_doctor_name,
                "preferred_date_raw": preferred_date_raw,
                "preferred_time_raw": preferred_time_raw,
                "preferred_date_confirmed": True,
                "preferred_time_confirmed": True,
            }

            if appointment.get("service_category_id"):
                request_updates["service_category_id"] = appointment.get("service_category_id")

            if appointment.get("service_name"):
                request_updates["service_category_name"] = appointment.get("service_name")

            if appointment.get("duration_minutes"):
                request_updates["duration_minutes"] = appointment.get("duration_minutes")

            try:
                (
                    supabase.table("appointment_requests")
                    .update(request_updates)
                    .eq("id", new_request.get("id"))
                    .execute()
                )
            except Exception as update_request_error:
                print(f"Could not update reschedule appointment request details: {update_request_error}")

        return {
            "ok": True,
            "status": "reschedule_request_created",
            "message_for_ai": (
                "Tell the caller the previous appointment has been cancelled, "
                "and the new appointment request has been noted. "
                "Do not say the new appointment is confirmed. "
                "Say the front desk will contact them to confirm."
            ),
            "cancelled_appointment": cancelled_appointment,
            "new_appointment_request": new_request,
            "selected_slot": {
                "doctor_id": doctor_id,
                "starts_at": start_time_iso,
                "ends_at": end_time_iso,
                "preferred_date_raw": preferred_date_raw,
                "preferred_time_raw": preferred_time_raw,
            },
        }

    except Exception as e:
        print(f"Error rescheduling appointment for AI: {e}")

        return {
            "ok": False,
            "reason": "reschedule_failed",
            "message_for_ai": "Tell the caller the front desk can help reschedule the appointment.",
        }

def normalize_persian_digits(text: str) -> str:
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    english_digits = "0123456789"

    for persian, english in zip(persian_digits, english_digits):
        text = text.replace(persian, english)

    for arabic, english in zip(arabic_digits, english_digits):
        text = text.replace(arabic, english)

    return text


def extract_hour_from_time_text(text: str) -> int | None:
    text = normalize_persian_digits(text.lower().strip())

    hour_map = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
    }

    for word, hour in hour_map.items():
        if word in text:
            if "pm" in text or "p.m" in text:
                if hour != 12:
                    hour += 12
            elif "am" in text or "a.m" in text:
                if hour == 12:
                    hour = 0
            elif any(marker in text for marker in ["عصر", "بعدازظهر", "بعد از ظهر", "شب"]):
                if hour != 12:
                    hour += 12

            return hour

    import re

    match = re.search(r"\b(\d{1,2})(?::\d{2})?\s*(am|pm|a\.m\.|p\.m\.)?\b", text)

    if not match:
        return None

    hour = int(match.group(1))
    suffix = match.group(2)

    if suffix:
        suffix = suffix.replace(".", "")

        if suffix == "pm" and hour != 12:
            hour += 12

        elif suffix == "am" and hour == 12:
            hour = 0

    elif any(marker in text for marker in ["عصر", "بعدازظهر", "بعد از ظهر", "شب"]):
        if hour != 12:
            hour += 12

    return hour


def extract_time_range_from_text(text: str) -> tuple[int, int] | None:
    text = normalize_persian_digits(text.lower().strip())

    import re

    range_patterns = [
        r"between\s+(.+?)\s+and\s+(.+)",
        r"from\s+(.+?)\s+to\s+(.+)",
        r"بین\s+(.+?)\s+تا\s+(.+)",
        r"از\s+(.+?)\s+تا\s+(.+)",
    ]

    for pattern in range_patterns:
        match = re.search(pattern, text)

        if not match:
            continue

        start_text = match.group(1).strip()
        end_text = match.group(2).strip()

        whole_text_has_pm_marker = any(
            marker in text
            for marker in ["pm", "p.m", "عصر", "بعدازظهر", "بعد از ظهر", "شب"]
        )

        if whole_text_has_pm_marker:
            start_has_pm_marker = any(
                marker in start_text
                for marker in ["pm", "p.m", "عصر", "بعدازظهر", "بعد از ظهر", "شب"]
            )

            end_has_pm_marker = any(
                marker in end_text
                for marker in ["pm", "p.m", "عصر", "بعدازظهر", "بعد از ظهر", "شب"]
            )

            if not start_has_pm_marker:
                start_text = start_text + " pm"

            if not end_has_pm_marker:
                end_text = end_text + " pm"

        start_hour = extract_hour_from_time_text(start_text)
        end_hour = extract_hour_from_time_text(end_text)

        if start_hour is None or end_hour is None:
            return None

        start_minutes = start_hour * 60
        end_minutes = end_hour * 60

        if end_minutes <= start_minutes:
            return None

        return start_minutes, end_minutes

    return None


def slot_matches_time_preference(
    slot: dict,
    preferred_time_raw: str | None,
    timezone_name: str = "America/Vancouver",
) -> bool:
    if not preferred_time_raw:
        return True

    text = normalize_persian_digits(preferred_time_raw.strip().lower())

    starts_at = slot.get("starts_at")
    if not starts_at:
        return True

    try:
        start_dt = datetime.fromisoformat(str(starts_at).replace("Z", "+00:00"))
        local_start = start_dt.astimezone(ZoneInfo(timezone_name))
        hour = local_start.hour
        minute = local_start.minute
        minutes = hour * 60 + minute
    except Exception:
        return True

    time_range = extract_time_range_from_text(text)

    if time_range:
        start_minutes, end_minutes = time_range
        return start_minutes <= minutes < end_minutes

    if "morning" in text or "صبح" in text:
        return 8 * 60 <= minutes < 12 * 60

    if "afternoon" in text or "بعدازظهر" in text or "بعد از ظهر" in text:
        return 12 * 60 <= minutes < 17 * 60

    if "evening" in text or "عصر" in text:
        return 17 * 60 <= minutes < 20 * 60

    if "before noon" in text or "before 12" in text or "قبل از ظهر" in text:
        return minutes < 12 * 60

    if "after noon" in text or "بعد از ظهر" in text:
        return minutes >= 12 * 60

    if "after" in text:
        parsed_hour = extract_hour_from_time_text(text)
        if parsed_hour is not None:
            return minutes >= parsed_hour * 60

    if "بعد از" in text or ("از" in text and "به بعد" in text):
        parsed_hour = extract_hour_from_time_text(text)
        if parsed_hour is not None:
            return minutes >= parsed_hour * 60

    if "before" in text:
        parsed_hour = extract_hour_from_time_text(text)
        if parsed_hour is not None:
            return minutes < parsed_hour * 60

    if "قبل از" in text or "تا قبل" in text:
        parsed_hour = extract_hour_from_time_text(text)
        if parsed_hour is not None:
            return minutes < parsed_hour * 60

    parsed_hour = extract_hour_from_time_text(text)

    if parsed_hour is not None:
        return hour == parsed_hour

    return True

def collapse_slots_by_time(slots: list[dict]) -> list[dict]:
    seen_start_times = set()
    collapsed_slots = []

    for slot in slots:
        starts_at = slot.get("starts_at")

        if not starts_at:
            continue

        if starts_at in seen_start_times:
            continue

        seen_start_times.add(starts_at)
        collapsed_slots.append(slot)

    return collapsed_slots
def get_booking_options_for_ai(
    clinic_id: str | None,
    doctors: list[dict],
    doctor_name: str | None,
    reason: str | None,
    preferred_date_raw: str | None = None,
    preferred_time_raw: str | None = None,
    preferred_date_confirmed: bool = False,
    timezone_name: str = "America/Vancouver",
) -> dict:
    if not clinic_id:
        return {
            "ok": False,
            "reason": "missing_clinic_id",
            "message_for_ai": "Tell the caller the front desk will contact them to arrange the appointment.",
        }

    if not doctors:
        return {
            "ok": False,
            "reason": "no_active_doctors",
            "message_for_ai": "Tell the caller the front desk will contact them because no active doctors are available.",
        }

    if not reason:
        return {
            "ok": False,
            "reason": "missing_reason",
            "message_for_ai": "Ask the caller for the reason for the dental visit.",
        }

    service_match = match_service_from_transcript(
        clinic_id=clinic_id,
        transcript=reason,
    )

    if not service_match:
        return {
            "ok": False,
            "reason": "service_not_matched",
            "message_for_ai": "Ask the caller to briefly repeat the reason for the dental visit.",
        }

    service_category_id = service_match.get("category_id")
    duration_minutes = service_match.get("duration_minutes") or 30

    if not service_category_id:
        return {
            "ok": False,
            "reason": "missing_service_category_id",
            "service": service_match,
            "message_for_ai": "Tell the caller the front desk will contact them to arrange the appointment.",
        }

    requested_doctor = match_doctor_from_name(
        doctors=doctors,
        preferred_doctor_name=doctor_name,
    )

    eligible_doctor_ids = get_service_category_doctor_ids(
        clinic_id=clinic_id,
        service_category_id=service_category_id,
    )

    if not eligible_doctor_ids:
        return {
            "ok": False,
            "reason": "no_doctors_for_service",
            "service": {
                "service_category_id": service_category_id,
                "service_name": service_match.get("category_name"),
                "canonical_reason": service_match.get("canonical_reason"),
                "duration_minutes": duration_minutes,
                "default_urgency": service_match.get("default_urgency"),
            },
            "message_for_ai": "Tell the caller the front desk will contact them because this treatment needs staff review.",
        }

    if requested_doctor:
        requested_doctor_id = requested_doctor.get("id")

        if requested_doctor_id not in eligible_doctor_ids:
            eligible_doctors = [
                doctor
                for doctor in doctors
                if doctor.get("id") in eligible_doctor_ids
            ]

            eligible_names = [
                get_doctor_display_name(doctor)
                for doctor in eligible_doctors
                if get_doctor_display_name(doctor)
            ]

            return {
                "ok": False,
                "reason": "requested_doctor_does_not_provide_service",
                "service": {
                    "service_category_id": service_category_id,
                    "service_name": service_match.get("category_name"),
                    "canonical_reason": service_match.get("canonical_reason"),
                    "duration_minutes": duration_minutes,
                    "default_urgency": service_match.get("default_urgency"),
                },
                "requested_doctor": {
                    "doctor_id": requested_doctor_id,
                    "doctor_name": get_doctor_display_name(requested_doctor),
                },
                "eligible_doctors": eligible_names,
                "message_for_ai": (
                    "Tell the caller the requested doctor does not provide that treatment, "
                    "then offer to check another eligible doctor."
                ),
            }

        doctors_to_search = [requested_doctor]

        doctor_filter = {
            "doctor_was_requested": True,
            "doctor_id": requested_doctor_id,
            "doctor_name": get_doctor_display_name(requested_doctor),
        }

    else:
        doctors_to_search = [
            doctor
            for doctor in doctors
            if doctor.get("id") in eligible_doctor_ids
        ]

        doctor_filter = {
            "doctor_was_requested": False,
            "doctor_id": None,
            "doctor_name": None,
        }

    if not doctors_to_search:
        return {
            "ok": False,
            "reason": "no_matching_active_doctors",
            "service": service_match,
            "message_for_ai": "Tell the caller the front desk will contact them to arrange the appointment.",
        }

    parsed_preferred_date = None

    if preferred_date_raw and preferred_date_confirmed:
        parsed_preferred_date = parse_preferred_date_raw(
            preferred_date_raw=preferred_date_raw,
            timezone_name=timezone_name,
        )

        if not parsed_preferred_date:
            return {
                "ok": False,
                "reason": "preferred_date_not_parsed",
                "service": service_match,
                "preferred_date_raw": preferred_date_raw,
                "message_for_ai": "Ask the caller to repeat the preferred date clearly.",
            }

    all_slots = []

    for doctor in doctors_to_search:
        doctor_id = doctor.get("id")

        if not doctor_id:
            continue

        if parsed_preferred_date:
            doctor_slots = find_next_available_slots_for_doctor(
                clinic_id=clinic_id,
                doctor_id=doctor_id,
                duration_minutes=duration_minutes,
                timezone_name=timezone_name,
                start_date=parsed_preferred_date,
                days_ahead=0,
                max_slots=2,
                step_minutes=duration_minutes,
            )
        else:
            doctor_slots = find_next_available_slots_for_doctor(
                clinic_id=clinic_id,
                doctor_id=doctor_id,
                duration_minutes=duration_minutes,
                timezone_name=timezone_name,
                start_date=None,
                days_ahead=60,
                max_slots=2,
                step_minutes=duration_minutes,
            )

        all_slots.extend(
            attach_doctor_name_to_slots(
                slots=doctor_slots,
                doctor=doctor,
            )
        )

    all_slots = sorted(
        all_slots,
        key=lambda slot: slot.get("starts_at") or "",
    )

    all_slots = collapse_slots_by_time(all_slots)

    if preferred_time_raw:
        time_filtered_slots = [
            slot
            for slot in all_slots
            if slot_matches_time_preference(
                slot=slot,
                preferred_time_raw=preferred_time_raw,
                timezone_name=timezone_name,
            )
        ]

        if time_filtered_slots:
            all_slots = time_filtered_slots
        else:
            return {
                "ok": False,
                "reason": "no_slots_for_time_preference",
                "service": {
                    "service_category_id": service_category_id,
                    "service_name": service_match.get("category_name"),
                    "canonical_reason": service_match.get("canonical_reason"),
                    "duration_minutes": duration_minutes,
                    "default_urgency": service_match.get("default_urgency"),
                },
                "doctor_filter": doctor_filter,
                "preferred_date_raw": preferred_date_raw,
                "preferred_time_raw": preferred_time_raw,
                "preferred_date_confirmed": preferred_date_confirmed,
                "message_for_ai": (
                    "Tell the caller there are no available times for that time preference, "
                    "and ask if another time of day works."
                ),
                "slots": [],
            }

    best_slots = all_slots[:2]

    if not best_slots:
        return {
            "ok": False,
            "reason": "no_slots_found",
            "service": {
                "service_category_id": service_category_id,
                "service_name": service_match.get("category_name"),
                "canonical_reason": service_match.get("canonical_reason"),
                "duration_minutes": duration_minutes,
                "default_urgency": service_match.get("default_urgency"),
            },
            "doctor_filter": doctor_filter,
            "preferred_date_raw": preferred_date_raw,
            "preferred_date_confirmed": preferred_date_confirmed,
            "message_for_ai": "Tell the caller no suitable slot was found and the front desk will contact them to find another time.",
        }

    return {
        "ok": True,
        "service": {
            "service_category_id": service_category_id,
            "service_name": service_match.get("category_name"),
            "canonical_reason": service_match.get("canonical_reason"),
            "duration_minutes": duration_minutes,
            "default_urgency": service_match.get("default_urgency"),
        },
        "doctor_filter": doctor_filter,
        "preferred_date": (
            parsed_preferred_date.isoformat()
            if parsed_preferred_date
            else None
        ),
        "preferred_date_raw": preferred_date_raw,
        "preferred_time_raw": preferred_time_raw,
        "preferred_date_confirmed": preferred_date_confirmed,
        "slots": best_slots,
        "message_for_ai": "Offer these appointment options to the caller and ask which one works better.",
    }


def get_active_clinic_faqs(clinic_id: str | None) -> list[dict]:
    if not supabase or not clinic_id:
        print("Cannot load clinic FAQs: missing supabase or clinic_id")
        return []

    try:
        result = (
            supabase.table("clinic_faqs")
            .select(
                """
                id,
                clinic_id,
                question,
                answer,
                category,
                keywords,
                is_active,
                sort_order,
                created_at,
                updated_at
                """
            )
            .eq("clinic_id", clinic_id)
            .eq("is_active", True)
            .order("sort_order")
            .order("created_at")
            .execute()
        )

        rows = result.data or []

        print(f"Loaded active FAQs for clinic={clinic_id}: {len(rows)} rows")

        return rows

    except Exception as e:
        print(f"Error loading clinic FAQs: {e}")
        return []


def score_faq_match(faq: dict, caller_text: str) -> int:
    normalized_text = normalize_search_text(caller_text)

    if not normalized_text:
        return 0

    question = normalize_search_text(faq.get("question"))
    answer = normalize_search_text(faq.get("answer"))
    category = normalize_search_text(faq.get("category"))

    raw_keywords = faq.get("keywords") or []

    if not isinstance(raw_keywords, list):
        raw_keywords = []

    keywords = [
        normalize_search_text(keyword)
        for keyword in raw_keywords
        if normalize_search_text(keyword)
    ]

    score = 0

    # Exact question match
    if question and normalized_text == question:
        score += 1000

    # Caller text contains the FAQ question or FAQ question contains caller text
    if question and question in normalized_text:
        score += 700

    if question and normalized_text in question:
        score += 500

    # Keyword matching
    for keyword in keywords:
        if not keyword:
            continue

        if keyword == normalized_text:
            score += 600

        elif keyword in normalized_text:
            score += 350 + len(keyword)

        elif normalized_text in keyword:
            score += 150

    # Category matching, weaker
    if category and category in normalized_text:
        score += 120

    # Word overlap between caller text and FAQ question/answer
    caller_words = [
        word for word in normalized_text.split()
        if len(word) >= 3
    ]

    searchable_text = " ".join(
        [
            question,
            answer,
            category,
            " ".join(keywords),
        ]
    )

    overlap_count = 0

    for word in caller_words:
        if word in searchable_text:
            overlap_count += 1

    score += overlap_count * 25

    # Penalize very weak one-word matches
    if score < 200 and overlap_count <= 1:
        return 0

    return score


def match_clinic_faq_from_text(
    clinic_id: str | None,
    caller_text: str | None,
    minimum_score: int = 250,
) -> dict | None:
    if not clinic_id or not caller_text:
        return None

    faqs = get_active_clinic_faqs(clinic_id)

    if not faqs:
        print("No active FAQs found")
        return None

    best_faq = None
    best_score = 0

    for faq in faqs:
        score = score_faq_match(faq, caller_text)

        if score > best_score:
            best_score = score
            best_faq = faq

    print(
        f"FAQ match result | text={caller_text} | "
        f"best_score={best_score} | best_faq={best_faq}"
    )

    if best_faq and best_score >= minimum_score:
        matched = dict(best_faq)
        matched["match_score"] = best_score
        return matched

    return None


def get_faq_answer_for_ai(
    clinic_id: str | None,
    caller_question: str | None,
) -> dict:
    if not supabase:
        return {
            "ok": False,
            "reason": "supabase_not_initialized",
            "message_for_ai": "Tell the caller the front desk can help with that question.",
            "faq": None,
        }

    if not clinic_id:
        return {
            "ok": False,
            "reason": "missing_clinic_id",
            "message_for_ai": "Tell the caller the front desk can help with that question.",
            "faq": None,
        }

    if not caller_question:
        return {
            "ok": False,
            "reason": "missing_question",
            "message_for_ai": "Ask the caller what they would like to know.",
            "faq": None,
        }

    faq = match_clinic_faq_from_text(
        clinic_id=clinic_id,
        caller_text=caller_question,
    )

    if not faq:
        return {
            "ok": False,
            "reason": "faq_not_found",
            "message_for_ai": (
                "Tell the caller you are not fully sure about that and "
                "offer to have the front desk follow up."
            ),
            "faq": None,
        }

    return {
        "ok": True,
        "status": "found",
        "message_for_ai": (
            "Answer the caller using the FAQ answer only. "
            "Do not invent extra clinic policies. "
            "If the answer says coverage, treatment, or availability depends on details, "
            "tell the caller the front desk can verify it."
        ),
        "faq": {
            "id": faq.get("id"),
            "question": faq.get("question"),
            "answer": faq.get("answer"),
            "category": faq.get("category"),
            "keywords": faq.get("keywords") or [],
            "match_score": faq.get("match_score"),
        },
    }


WEEKDAY_NAMES_BY_DB_DAY = {
    0: "Sunday",
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
}


def get_next_date_for_weekday(
    weekday_name: str,
    timezone_name: str = "America/Vancouver",
) -> date | None:
    if not weekday_name:
        return None

    normalized = normalize_search_text(weekday_name)

    weekday_map = {
        "monday": 0,
        "mon": 0,
        "tuesday": 1,
        "tue": 1,
        "wednesday": 2,
        "wed": 2,
        "thursday": 3,
        "thu": 3,
        "friday": 4,
        "fri": 4,
        "saturday": 5,
        "sat": 5,
        "sunday": 6,
        "sun": 6,
    }

    wanted_weekday = weekday_map.get(normalized)

    if wanted_weekday is None:
        return None

    tz = ZoneInfo(timezone_name)
    today = datetime.now(tz).date()

    days_ahead = (wanted_weekday - today.weekday()) % 7

    return today + timedelta(days=days_ahead)


def parse_working_hours_date_raw(
    date_raw: str | None,
    timezone_name: str = "America/Vancouver",
) -> date | None:
    if not date_raw:
        return None

    text = str(date_raw).strip()

    if not text:
        return None

    normalized = normalize_search_text(text)

    tz = ZoneInfo(timezone_name)
    today = datetime.now(tz).date()

    if normalized == "today":
        return today

    if normalized == "tomorrow":
        return today + timedelta(days=1)

    weekday_date = get_next_date_for_weekday(
        weekday_name=text,
        timezone_name=timezone_name,
    )

    if weekday_date:
        return weekday_date

    return parse_preferred_date_raw(
        preferred_date_raw=text,
        timezone_name=timezone_name,
    )


def format_db_time_for_ai(value) -> str | None:
    parsed_time = parse_db_time(value)

    if not parsed_time:
        return None

    value_as_datetime = datetime(
        2000,
        1,
        1,
        parsed_time.hour,
        parsed_time.minute,
        parsed_time.second,
    )

    if parsed_time.minute == 0:
        return value_as_datetime.strftime("%I %p").lstrip("0")

    return value_as_datetime.strftime("%I:%M %p").lstrip("0")


def get_calendar_availability_rules_for_scope(
    clinic_id: str | None,
    doctor_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    if not supabase or not clinic_id:
        print("Cannot load availability rules: missing supabase or clinic_id")
        return []

    try:
        query = (
            supabase.table("calendar_availability_rules")
            .select("*")
            .eq("clinic_id", clinic_id)
            .eq("is_active", True)
        )

        if doctor_id:
            query = query.eq("doctor_id", doctor_id)
        else:
            query = query.is_("doctor_id", "null")

        if start_date and end_date:
            query = (
                query
                .lte("start_date", end_date.isoformat())
                .or_(f"end_date.is.null,end_date.gte.{start_date.isoformat()}")
            )

        result = (
            query
            .order("day_of_week")
            .order("start_time")
            .execute()
        )

        rows = result.data or []

        print(
            f"Loaded availability rules for scope | "
            f"clinic_id={clinic_id} | doctor_id={doctor_id} | "
            f"start_date={start_date} | end_date={end_date} | rows={rows}"
        )

        return rows

    except Exception as e:
        print(f"Error loading availability rules for scope: {e}")
        return []


def summarize_weekly_working_hours_from_rules(
    rules: list[dict],
) -> list[dict]:
    grouped: dict[int, list[str]] = {
        0: [],
        1: [],
        2: [],
        3: [],
        4: [],
        5: [],
        6: [],
    }

    for rule in rules:
        repeat_type = rule.get("repeat_type") or "none"

        start_display = format_db_time_for_ai(rule.get("start_time"))
        end_display = format_db_time_for_ai(rule.get("end_time"))

        if not start_display or not end_display:
            continue

        interval_display = f"{start_display} to {end_display}"

        if repeat_type == "daily":
            target_db_days = [0, 1, 2, 3, 4, 5, 6]

        elif repeat_type == "weekdays":
            target_db_days = [1, 2, 3, 4, 5]

        elif repeat_type in ["weekly", "custom"]:
            db_day = rule.get("day_of_week")
            target_db_days = [db_day] if db_day in grouped else []

        elif repeat_type == "none":
            start_date_raw = rule.get("start_date")
            target_db_days = []

            if start_date_raw:
                try:
                    rule_date = date.fromisoformat(str(start_date_raw))
                    target_db_days = [python_day_to_db_day(rule_date)]
                except Exception:
                    target_db_days = []

        else:
            target_db_days = []

        for db_day in target_db_days:
            if db_day not in grouped:
                continue

            if interval_display not in grouped[db_day]:
                grouped[db_day].append(interval_display)

    weekly_hours = []

    for db_day in [1, 2, 3, 4, 5, 6, 0]:
        intervals = grouped.get(db_day) or []
        day_name = WEEKDAY_NAMES_BY_DB_DAY.get(db_day, "Unknown")

        weekly_hours.append(
            {
                "day_of_week": db_day,
                "day_name": day_name,
                "intervals": intervals,
                "is_closed": len(intervals) == 0,
                "display": (
                    f"{day_name}: {', '.join(intervals)}"
                    if intervals
                    else f"{day_name}: closed"
                ),
            }
        )

    return weekly_hours


def format_working_hours_intervals_for_ai(
    intervals: list[tuple[datetime, datetime]],
) -> list[dict]:
    formatted = []

    for start_dt, end_dt in intervals:
        formatted.append(
            {
                "starts_at": start_dt.isoformat(),
                "ends_at": end_dt.isoformat(),
                "start_time": start_dt.strftime("%H:%M"),
                "end_time": end_dt.strftime("%H:%M"),
                "display": f"{format_time_for_ai(start_dt)} to {format_time_for_ai(end_dt)}",
            }
        )

    return formatted


def get_working_hours_for_ai(
    clinic_id: str | None,
    doctors: list[dict] | None = None,
    caller_question: str | None = None,
    doctor_name: str | None = None,
    date_raw: str | None = None,
    timezone_name: str = "America/Vancouver",
) -> dict:
    if not supabase:
        return {
            "ok": False,
            "reason": "supabase_not_initialized",
            "message_for_ai": "Tell the caller the front desk can help verify the hours.",
        }

    if not clinic_id:
        return {
            "ok": False,
            "reason": "missing_clinic_id",
            "message_for_ai": "Tell the caller the front desk can help verify the hours.",
        }

    doctors = doctors or []

    matched_doctor = None

    if doctor_name:
        matched_doctor = match_doctor_from_name(
            doctors=doctors,
            preferred_doctor_name=doctor_name,
        )

    if not matched_doctor and caller_question:
        matched_doctor = match_doctor_from_name(
            doctors=doctors,
            preferred_doctor_name=caller_question,
        )

    target_doctor_id = matched_doctor.get("id") if matched_doctor else None
    target_doctor_name = (
        get_doctor_display_name(matched_doctor)
        if matched_doctor
        else None
    )

    target_date = parse_working_hours_date_raw(
        date_raw=date_raw,
        timezone_name=timezone_name,
    )

    if not target_date and caller_question:
        target_date = parse_working_hours_date_raw(
            date_raw=caller_question,
            timezone_name=timezone_name,
        )

    scope = "doctor" if target_doctor_id else "clinic"
    scope_name = target_doctor_name or "the clinic"

    if target_date:
        rules = get_calendar_availability_rules_for_scope(
            clinic_id=clinic_id,
            doctor_id=target_doctor_id,
            start_date=target_date,
            end_date=target_date,
        )

        if not rules:
            return {
                "ok": True,
                "status": "no_hours_found",
                "scope": scope,
                "scope_name": scope_name,
                "doctor": (
                    {
                        "doctor_id": target_doctor_id,
                        "doctor_name": target_doctor_name,
                    }
                    if target_doctor_id
                    else None
                ),
                "date": target_date.isoformat(),
                "intervals": [],
                "message_for_ai": (
                    f"Tell the caller no working hours were found for {scope_name} on that date. "
                    "Say the front desk can verify the hours."
                ),
            }

        rule_ids = [
            rule.get("id")
            for rule in rules
            if rule.get("id")
        ]

        exceptions = get_calendar_availability_exceptions_for_rules(
            clinic_id=clinic_id,
            rule_ids=rule_ids,
            start_date=target_date,
            end_date=target_date,
        )

        intervals = get_daily_available_intervals_from_rules(
            rules=rules,
            exceptions=exceptions,
            target_date=target_date,
            timezone_name=timezone_name,
        )

        formatted_intervals = format_working_hours_intervals_for_ai(intervals)

        if not formatted_intervals:
            return {
                "ok": True,
                "status": "closed",
                "scope": scope,
                "scope_name": scope_name,
                "doctor": (
                    {
                        "doctor_id": target_doctor_id,
                        "doctor_name": target_doctor_name,
                    }
                    if target_doctor_id
                    else None
                ),
                "date": target_date.isoformat(),
                "intervals": [],
                "message_for_ai": (
                    f"Tell the caller {scope_name} appears to be closed on that date. "
                    "Say the front desk can verify if needed."
                ),
            }

        return {
            "ok": True,
            "status": "found",
            "scope": scope,
            "scope_name": scope_name,
            "doctor": (
                {
                    "doctor_id": target_doctor_id,
                    "doctor_name": target_doctor_name,
                }
                if target_doctor_id
                else None
            ),
            "date": target_date.isoformat(),
            "intervals": formatted_intervals,
            "message_for_ai": (
                f"Tell the caller {scope_name}'s working hours for that date. "
                "Use only the returned intervals. Keep the answer short."
            ),
        }

    rules = get_calendar_availability_rules_for_scope(
        clinic_id=clinic_id,
        doctor_id=target_doctor_id,
    )

    if not rules:
        return {
            "ok": False,
            "reason": "no_working_hours_found",
            "scope": scope,
            "scope_name": scope_name,
            "doctor": (
                {
                    "doctor_id": target_doctor_id,
                    "doctor_name": target_doctor_name,
                }
                if target_doctor_id
                else None
            ),
            "message_for_ai": (
                f"Tell the caller working hours for {scope_name} are not available in the system, "
                "and the front desk can verify them."
            ),
        }

    weekly_hours = summarize_weekly_working_hours_from_rules(rules)

    return {
        "ok": True,
        "status": "found",
        "scope": scope,
        "scope_name": scope_name,
        "doctor": (
            {
                "doctor_id": target_doctor_id,
                "doctor_name": target_doctor_name,
            }
            if target_doctor_id
            else None
        ),
        "weekly_hours": weekly_hours,
        "message_for_ai": (
            f"Tell the caller {scope_name}'s working hours using weekly_hours. "
            "Keep the answer short. Do not invent hours."
        ),
    }

def get_patient_birth_year(patient: dict | None) -> int | None:
    if not patient:
        return None

    raw_date = patient.get("date_of_birth")

    if not raw_date:
        return None

    try:
        return int(str(raw_date)[:4])
    except Exception:
        return None


def get_patient_display_name(patient: dict | None) -> str:
    if not patient:
        return "this patient"

    return (
        patient.get("full_name")
        or patient.get("patient_name")
        or "this patient"
    )


def build_patient_options_for_ai(patients: list[dict]) -> list[dict]:
    options = []

    for patient in patients or []:
        patient_id = patient.get("id")
        full_name = get_patient_display_name(patient)

        if not patient_id or not full_name:
            continue

        options.append(
            {
                "id": patient_id,
                "full_name": full_name,
                "date_of_birth": patient.get("date_of_birth"),
                "birth_year": get_patient_birth_year(patient),
                "phone_primary": patient.get("phone_primary"),
                "phone_secondary": patient.get("phone_secondary"),
            }
        )

    return options