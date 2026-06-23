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
        keyword_result = (
            supabase.table("service_keywords")
            .select("id, category_id, keyword, language, match_type")
            .eq("clinic_id", clinic_id)
            .eq("is_active", True)
            .execute()
        )

        transcript_lower = normalize_search_text(transcript)

        best_match = None
        best_keyword_length = 0

        for row in keyword_result.data or []:
            keyword = (row.get("keyword") or "").strip()
            category_id = row.get("category_id")

            if not keyword or not category_id:
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

        category_id = best_match.get("category_id")

        category_result = (
            supabase.table("service_categories")
            .select(
                "id, name, canonical_reason, default_urgency, "
                "creates_appointment_request, default_duration_minutes"
            )
            .eq("id", category_id)
            .eq("clinic_id", clinic_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )

        if not category_result.data:
            print(f"Matched keyword but no active service category found: {category_id}")
            return None

        category = category_result.data[0]

        matched_service = {
            "keyword": best_match.get("keyword"),
            "category_id": category.get("id"),
            "category_name": category.get("name"),
            "canonical_reason": category.get("canonical_reason"),
            "default_urgency": category.get("default_urgency") or "normal",
            "creates_appointment_request": bool(category.get("creates_appointment_request")),
            "duration_minutes": category.get("default_duration_minutes") or 30,
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


def format_slot_for_ai(slot_start: datetime, slot_end: datetime) -> str:
    day_name = slot_start.strftime("%A")
    month_name = slot_start.strftime("%B")
    day_number = slot_start.day

    start_display = slot_start.strftime("%I:%M %p").lstrip("0")
    end_display = slot_end.strftime("%I:%M %p").lstrip("0")

    return f"{day_name}, {month_name} {day_number} from {start_display} to {end_display}"



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
        slot_copy["doctor_name"] = doctor_name

        if doctor_name and slot.get("display"):
            slot_copy["display"] = f"{doctor_name} on {slot.get('display')}"

        enriched_slots.append(slot_copy)

    return enriched_slots


def get_booking_options_for_ai(
    clinic_id: str | None,
    doctors: list[dict],
    doctor_name: str | None,
    reason: str | None,
    preferred_date_raw: str | None = None,
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
        "preferred_date_confirmed": preferred_date_confirmed,
        "slots": best_slots,
        "message_for_ai": "Offer these appointment options to the caller and ask which one works better.",
    }

def create_call_session(
    clinic_id: str | None,
    call_id: str | None,
    twilio_call_sid: str | None,
    caller_phone: str | None,
    current_state: str = "collect_reason",
    pending_question: str | None = "reason",
    language: str | None = "en",
):
    if not supabase:
        print("Supabase client is not initialized")
        return None

    try:
        payload = {
            "clinic_id": clinic_id,
            "call_id": call_id,
            "twilio_call_sid": twilio_call_sid,
            "caller_phone": normalize_phone(caller_phone),
            "current_state": current_state,
            "pending_question": pending_question,
            "language": language or "en",
        }

        print(f"Inserting call session payload: {payload}")

        result = supabase.table("call_sessions").insert(payload).execute()

        print(f"Call session insert result: {result.data}")

        if result.data:
            return result.data[0]

        return None

    except Exception as e:
        print(f"Error creating call session: {e}")
        return None


def get_call_session_by_twilio_sid(twilio_call_sid: str | None):
    if not supabase or not twilio_call_sid:
        print("Cannot get call session: missing supabase or twilio_call_sid")
        return None

    try:
        result = (
            supabase.table("call_sessions")
            .select("*")
            .eq("twilio_call_sid", twilio_call_sid)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if result.data:
            return result.data[0]

        return None

    except Exception as e:
        print(f"Error loading call session: {e}")
        return None


def update_call_session(call_session_id: str, updates: dict):
    if not supabase:
        print("Supabase client is not initialized")
        return None

    if not call_session_id:
        print("Cannot update call session: missing call_session_id")
        return None

    try:
        print(f"Updating call session {call_session_id}: {updates}")

        result = (
            supabase.table("call_sessions")
            .update(updates)
            .eq("id", call_session_id)
            .execute()
        )

        print(f"Call session update result: {result.data}")

        if result.data:
            return result.data[0]

        return None

    except Exception as e:
        print(f"Error updating call session: {e}")
        return None


def get_next_turn_index(call_session_id: str | None) -> int:
    if not supabase or not call_session_id:
        return 1

    try:
        result = (
            supabase.table("call_turn_logs")
            .select("turn_index")
            .eq("call_session_id", call_session_id)
            .order("turn_index", desc=True)
            .limit(1)
            .execute()
        )

        if result.data and result.data[0].get("turn_index") is not None:
            return int(result.data[0]["turn_index"]) + 1

        return 1

    except Exception as e:
        print(f"Error getting next turn index: {e}")
        return 1


def save_call_turn_log(
    call_session_id: str | None,
    call_id: str | None,
    twilio_call_sid: str | None,
    role: str,
    raw_text: str | None = None,
    cleaned_text: str | None = None,
    parsed_intent: str | None = None,
    parsed_entities: dict | None = None,
    confidence: float | None = None,
    state_before: str | None = None,
    state_after: str | None = None,
    backend_action: str | None = None,
    backend_response: str | None = None,
    fallback_triggered: bool = False,
    fallback_reason: str | None = None,
    error_message: str | None = None,
):
    if not supabase:
        print("Supabase client is not initialized")
        return None

    try:
        turn_index = get_next_turn_index(call_session_id)

        payload = {
            "call_session_id": call_session_id,
            "call_id": call_id,
            "twilio_call_sid": twilio_call_sid,
            "turn_index": turn_index,
            "role": role,
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "parsed_intent": parsed_intent,
            "parsed_entities": parsed_entities or {},
            "confidence": confidence,
            "state_before": state_before,
            "state_after": state_after,
            "backend_action": backend_action,
            "backend_response": backend_response,
            "fallback_triggered": fallback_triggered,
            "fallback_reason": fallback_reason,
            "error_message": error_message,
        }

        print(f"Inserting call turn log payload: {payload}")

        result = supabase.table("call_turn_logs").insert(payload).execute()

        print(f"Call turn log insert result: {result.data}")

        if result.data:
            return result.data[0]

        return None

    except Exception as e:
        print(f"Error saving call turn log: {e}")
        return None
    
def get_local_parser_rules(clinic_id: str | None = None, language: str | None = None):
    if not supabase:
        print("Supabase client is not initialized")
        return []

    try:
        query = (
            supabase.table("local_parser_rules")
            .select("*")
            .eq("is_active", True)
            .order("priority", desc=False)
        )

        # Rules:
        # 1. global rules: clinic_id is null
        # 2. clinic-specific rules: clinic_id = current clinic
        if clinic_id:
            query = query.or_(f"clinic_id.is.null,clinic_id.eq.{clinic_id}")
        else:
            query = query.is_("clinic_id", "null")

        if language:
            query = query.in_("language", [language, "any"])

        result = query.execute()

        return result.data or []

    except Exception as e:
        print(f"Error loading local parser rules: {e}")
        return []