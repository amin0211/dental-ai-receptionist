import os
from urllib.parse import urlparse
import json
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response
from supabase import create_client, Client
from openai import AsyncOpenAI
from rapidfuzz import fuzz

from config import (
    OPENAI_API_KEY,
    OPENAI_EXTRACTION_MODEL,
    PUBLIC_BASE_URL,
    PUBLIC_WS_URL,
)

from realtime_routes import router as realtime_router

from supabase_service import (
    normalize_phone,
    find_clinic_by_twilio_number,
    save_call_to_db,
    create_appointment_request,
    update_appointment_request,
    update_call,
    match_service_from_transcript,
    save_call_extraction,
    get_active_doctors_for_clinic,
    match_doctor_from_name,
    get_booking_options_for_ai,
    create_call_session,
    get_call_session_by_twilio_sid,
    update_call_session,
    save_call_turn_log,
    get_local_parser_rules,
    get_active_service_keywords_for_clinic,
)

app = FastAPI()
app.include_router(realtime_router)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# ---------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------

def now_ms() -> float:
    return time.perf_counter() * 1000


def log_timing(label: str, start_ms: float, extra: str = ""):
    elapsed = now_ms() - start_ms
    if extra:
        print(f"[TIMING] {label}: {elapsed:.1f}ms | {extra}")
    else:
        print(f"[TIMING] {label}: {elapsed:.1f}ms")


# ---------------------------------------------------------------------
# XML / Twilio helpers
# ---------------------------------------------------------------------

def xml_escape(value: str | None) -> str:
    if not value:
        return ""

    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def twiml_gather(
    message: str,
    action_url: str,
    language: str = "en-US",
    timeout: int = 3,
    speech_timeout: str = "1",
) -> Response:
    safe_message = xml_escape(message)
    safe_action = xml_escape(action_url)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech"
            action="{safe_action}"
            method="POST"
            language="{language}"
            timeout="{timeout}"
            speechTimeout="{speech_timeout}">
        <Say voice="alice" language="{language}">
            {safe_message}
        </Say>
    </Gather>
    <Redirect method="POST">{safe_action}</Redirect>
</Response>
"""
    return Response(content=twiml, media_type="application/xml")


def twiml_say_and_hangup(message: str, language: str = "en-US") -> Response:
    safe_message = xml_escape(message)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="{language}">
        {safe_message}
    </Say>
    <Hangup />
</Response>
"""
    return Response(content=twiml, media_type="application/xml")


def twiml_connect_realtime(
    caller_phone: str | None,
    to_number: str | None,
    call_sid: str | None,
    intro_message: str = "I’ll connect you to the AI receptionist now.",
) -> Response:
    safe_intro = xml_escape(intro_message)
    safe_caller = xml_escape(normalize_phone(caller_phone))
    safe_to = xml_escape(normalize_phone(to_number))
    safe_call_sid = xml_escape(call_sid or "")

    stream_url = f"{PUBLIC_WS_URL}/twilio/realtime"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="en-US">
        {safe_intro}
    </Say>
    <Connect>
        <Stream url="{xml_escape(stream_url)}">
            <Parameter name="caller_phone" value="{safe_caller}" />
            <Parameter name="to_number" value="{safe_to}" />
            <Parameter name="call_sid" value="{safe_call_sid}" />
        </Stream>
    </Connect>
</Response>
"""
    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------
# Template responses
# ---------------------------------------------------------------------

def template_greeting() -> str:
    return "Hi, thanks for calling Westview Dental. How can I help you today?"


def template_ask_reason() -> str:
    return "Can you briefly tell me what dental problem or visit type you need help with?"


def template_clarify_reason() -> str:
    return "Can you briefly tell me what kind of dental problem it is?"


def template_service_menu() -> str:
    return "Is it tooth pain, a broken tooth, cleaning or checkup, or something else?"


def template_service_menu_retry() -> str:
    return "Sorry, I didn’t catch that. Is it tooth pain, a broken tooth, cleaning, checkup, or something else?"


def template_confirm_service(service_name: str | None) -> str:
    if service_name:
        return f"I may have heard {service_name}. Is that correct?"
    return "I may have heard the dental issue, but I want to confirm. Is that correct?"


def template_confirm_date(date_text: str) -> str:
    return f"Is {date_text} correct?"


def template_ask_date() -> str:
    return "What date would you prefer for the appointment?"


def template_ask_slot_choice_again() -> str:
    return "Did you prefer the first option or the second option?"


def template_no_slots_found() -> str:
    return "I couldn’t find a matching time, so the front desk will contact you to help schedule."


def template_front_desk_followup() -> str:
    return "I’ll have the front desk contact you to help schedule this."


def template_doctor_not_found(name: str | None) -> str:
    if name:
        return f"I couldn’t find {name} at this clinic. Would you like the soonest available doctor?"
    return "I couldn’t find that doctor at this clinic. Would you like the soonest available doctor?"


def template_doctor_does_not_provide_service(doctor_name: str | None) -> str:
    if doctor_name:
        return f"{doctor_name} does not provide that treatment. Would you like me to check another available doctor?"
    return "That doctor does not provide that treatment. Would you like me to check another available doctor?"


def template_emergency() -> str:
    return (
        "If you have trouble breathing, severe facial swelling, uncontrolled bleeding, "
        "or facial trauma, please seek emergency medical care immediately. "
        "I’ll mark this as urgent for the front desk."
    )


def format_slot_display_fallback(slot: dict) -> str:
    doctor_name = slot.get("doctor_name") or "the dentist"
    date_text = slot.get("date") or ""
    start_time = slot.get("start_time") or ""
    return f"{doctor_name} on {date_text} at {start_time}".strip()


def format_slot_offer(slots: list[dict]) -> str:
    if not slots:
        return template_no_slots_found()

    if len(slots) == 1:
        first = slots[0]
        display = first.get("display") or format_slot_display_fallback(first)
        return f"I found one option: {display}. Does that work for you?"

    first = slots[0]
    second = slots[1]

    first_display = first.get("display") or format_slot_display_fallback(first)
    second_display = second.get("display") or format_slot_display_fallback(second)

    return (
        f"I found two options: {first_display}, or {second_display}. "
        "Which one works better?"
    )


def template_final_noted(slot: dict) -> str:
    display = slot.get("display") or format_slot_display_fallback(slot)
    return (
        f"I’ve noted your request for {display}. "
        "The front desk will contact you to confirm."
    )


# ---------------------------------------------------------------------
# Local parser cache
# ---------------------------------------------------------------------

LOCAL_RULE_CACHE: dict[str, dict] = {}
LOCAL_RULE_CACHE_TTL_SECONDS = int(os.environ.get("LOCAL_RULE_CACHE_TTL_SECONDS", "300"))

SERVICE_KEYWORD_CACHE: dict[str, dict] = {}
SERVICE_KEYWORD_CACHE_TTL_SECONDS = int(os.environ.get("SERVICE_KEYWORD_CACHE_TTL_SECONDS", "300"))


def normalize_parser_text(text: str | None) -> str:
    value = (text or "").strip().lower()

    replacements = {
        "ي": "ی",
        "ك": "ک",
        "أ": "ا",
        "إ": "ا",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    punctuation = [
        ".", ",", "!", "?", ";", ":", '"', "'", "’", "‘",
        "(", ")", "[", "]", "{", "}", "-", "_"
    ]

    for mark in punctuation:
        value = value.replace(mark, " ")

    value = " ".join(value.split())
    return value


def detect_simple_language(text: str | None, fallback: str = "en") -> str:
    value = text or ""

    for char in value:
        if "\u0600" <= char <= "\u06FF":
            return "fa"

    return fallback or "en"


def get_rules_cache_key(clinic_id: str | None, language: str) -> str:
    return f"{clinic_id or 'global'}:{language or 'en'}"


def get_cached_local_parser_rules(clinic_id: str | None, language: str) -> list[dict]:
    cache_key = get_rules_cache_key(clinic_id, language)
    now = time.time()

    cached = LOCAL_RULE_CACHE.get(cache_key)

    if cached and now - cached.get("loaded_at", 0) < LOCAL_RULE_CACHE_TTL_SECONDS:
        return cached.get("rules", [])

    load_start_ms = now_ms()

    rules = get_local_parser_rules(
        clinic_id=clinic_id,
        language=language,
    )

    LOCAL_RULE_CACHE[cache_key] = {
        "loaded_at": now,
        "rules": rules,
    }

    log_timing(
        "Supabase load local_parser_rules into cache",
        load_start_ms,
        f"clinic_id={clinic_id} language={language} rule_count={len(rules)}",
    )

    return rules


def local_rule_matches(text: str, phrase: str, match_type: str) -> bool:
    normalized_text = normalize_parser_text(text)
    normalized_phrase = normalize_parser_text(phrase)

    if not normalized_phrase:
        return False

    if match_type == "exact":
        return normalized_text == normalized_phrase

    if match_type == "starts_with":
        return normalized_text.startswith(normalized_phrase)

    if match_type == "contains":
        return normalized_phrase in normalized_text

    if match_type == "regex":
        return False

    return normalized_phrase in normalized_text


def build_parsed_from_local_rule(
    rule: dict,
    caller_text: str,
    session: dict,
    language: str,
) -> dict:
    intent = rule.get("intent") or "unclear"
    entity_key = rule.get("entity_key")
    entity_value = rule.get("entity_value") or {}

    parsed = {
        "intent": intent,
        "reason": None,
        "reason_is_specific_enough": False,
        "doctor_name": None,
        "preferred_date_raw": None,
        "date_confirmation": None,
        "slot_choice": None,
        "wants_repeat": False,
        "is_emergency": False,
        "is_unclear": False,
        "language": language or session.get("language") or "en",
        "confidence": float(rule.get("confidence") or 0.95),
        "notes": f"Matched local parser rule: {rule.get('phrase')}",
    }

    if intent == "repeat":
        parsed["wants_repeat"] = True

    if intent == "provide_reason":
        parsed["reason"] = caller_text

    if intent == "emergency":
        parsed["reason"] = caller_text
        parsed["reason_is_specific_enough"] = True
        parsed["is_emergency"] = True

    if entity_key and isinstance(entity_value, dict):
        value = entity_value.get("value")

        if entity_key == "slot_choice":
            parsed["slot_choice"] = int(value) if value is not None else None

        elif entity_key == "date_confirmation":
            parsed["date_confirmation"] = bool(value)

        elif entity_key == "reason_is_specific_enough":
            parsed["reason_is_specific_enough"] = bool(value)

        elif entity_key == "is_emergency":
            parsed["is_emergency"] = bool(value)

    return parsed


def classify_simple_turn_locally(caller_text: str, session: dict) -> dict | None:
    local_start_ms = now_ms()
    text = normalize_parser_text(caller_text)

    if not text:
        parsed = {
            "intent": "unclear",
            "reason": None,
            "reason_is_specific_enough": False,
            "doctor_name": None,
            "preferred_date_raw": None,
            "date_confirmation": None,
            "slot_choice": None,
            "wants_repeat": False,
            "is_emergency": False,
            "is_unclear": True,
            "language": session.get("language") or "en",
            "confidence": 0.0,
            "notes": "Empty speech.",
        }

        log_timing(
            "Local classify_simple_turn_locally",
            local_start_ms,
            "intent=unclear reason=empty",
        )

        return parsed

    current_state = session.get("current_state") or "collect_reason"

    yes_words = ["yes", "yeah", "yep", "correct", "right", "that is correct", "that works"]
    no_words = ["no", "nope", "not correct", "wrong", "nah"]

    if current_state in ["date_confirmation", "confirm_service"]:
        if text in yes_words or any(word in text for word in ["that is correct", "that works"]):
            parsed = {
                "intent": "confirm_date",
                "reason": None,
                "reason_is_specific_enough": False,
                "doctor_name": None,
                "preferred_date_raw": None,
                "date_confirmation": True,
                "slot_choice": None,
                "wants_repeat": False,
                "is_emergency": False,
                "is_unclear": False,
                "language": session.get("language") or "en",
                "confidence": 0.98,
                "notes": "Matched local yes confirmation.",
            }
            log_timing("Local classify_simple_turn_locally", local_start_ms, "intent=confirm_date")
            return parsed

        if text in no_words:
            parsed = {
                "intent": "reject_date",
                "reason": None,
                "reason_is_specific_enough": False,
                "doctor_name": None,
                "preferred_date_raw": None,
                "date_confirmation": False,
                "slot_choice": None,
                "wants_repeat": False,
                "is_emergency": False,
                "is_unclear": False,
                "language": session.get("language") or "en",
                "confidence": 0.98,
                "notes": "Matched local no rejection.",
            }
            log_timing("Local classify_simple_turn_locally", local_start_ms, "intent=reject_date")
            return parsed

    vague_reason_words = [
        "problem",
        "issue",
        "something wrong",
        "concern",
        "help",
    ]

    if current_state in ["collect_reason", "clarify_reason"] and any(
        word in text for word in vague_reason_words
    ):
        parsed = {
            "intent": "vague_reason",
            "reason": caller_text,
            "reason_is_specific_enough": False,
            "doctor_name": None,
            "preferred_date_raw": None,
            "date_confirmation": None,
            "slot_choice": None,
            "wants_repeat": False,
            "is_emergency": False,
            "is_unclear": False,
            "language": session.get("language") or "en",
            "confidence": 0.98,
            "notes": "Matched local vague reason. Route to service_menu.",
        }

        log_timing(
            "Local classify_simple_turn_locally",
            local_start_ms,
            f"intent=vague_reason text={text}",
        )

        return parsed

    language = detect_simple_language(
        caller_text,
        fallback=session.get("language") or "en",
    )

    clinic_id = session.get("clinic_id")

    rules = get_cached_local_parser_rules(
        clinic_id=clinic_id,
        language=language,
    )

    best_match = None

    for rule in rules:
        rule_state = rule.get("current_state")

        if rule_state and rule_state != current_state:
            continue

        phrase = rule.get("phrase") or ""
        match_type = rule.get("match_type") or "contains"

        if local_rule_matches(text, phrase, match_type):
            best_match = rule
            break

    if not best_match:
        log_timing(
            "Local classify_simple_turn_locally",
            local_start_ms,
            f"no_match language={language} state={current_state}",
        )
        return None

    parsed = build_parsed_from_local_rule(
        rule=best_match,
        caller_text=caller_text,
        session=session,
        language=language,
    )

    log_timing(
        "Local classify_simple_turn_locally",
        local_start_ms,
        f"intent={parsed.get('intent')} phrase={best_match.get('phrase')}",
    )

    return parsed


# ---------------------------------------------------------------------
# Service resolver and controlled service menu
# ---------------------------------------------------------------------

def get_cached_service_keywords(clinic_id: str | None) -> list[dict]:
    if not clinic_id:
        return []

    cache_key = clinic_id
    now = time.time()

    cached = SERVICE_KEYWORD_CACHE.get(cache_key)

    if cached and now - cached.get("loaded_at", 0) < SERVICE_KEYWORD_CACHE_TTL_SECONDS:
        return cached.get("keywords", [])

    load_start_ms = now_ms()

    keywords = get_active_service_keywords_for_clinic(clinic_id)

    SERVICE_KEYWORD_CACHE[cache_key] = {
        "loaded_at": now,
        "keywords": keywords,
    }

    log_timing(
        "Supabase load service_keywords into cache",
        load_start_ms,
        f"clinic_id={clinic_id} keyword_count={len(keywords)}",
    )

    return keywords


def normalize_service_text(text: str | None) -> str:
    value = normalize_parser_text(text)

    replacements = {
        "tooths": "tooth",
        "toothes": "tooth",
        "teefs": "teeth",
    }

    words = value.split()
    normalized_words = [replacements.get(word, word) for word in words]

    return " ".join(normalized_words)


def build_service_candidate(row: dict) -> dict | None:
    category = row.get("service_categories") or {}

    if not category:
        return None

    return {
        "service_category_id": category.get("id") or row.get("category_id"),
        "service_category_name": category.get("name"),
        "canonical_reason": category.get("canonical_reason"),
        "duration_minutes": category.get("default_duration_minutes") or 30,
        "urgency": category.get("default_urgency") or "normal",
        "matched_keyword": row.get("keyword"),
    }


def resolve_service_locally(caller_text: str, clinic_id: str | None) -> dict:
    resolver_start_ms = now_ms()

    raw_text = caller_text or ""
    normalized_text = normalize_service_text(raw_text)

    if not normalized_text or not clinic_id:
        return {
            "status": "no_match",
            "confidence": 0.0,
            "raw_text": raw_text,
            "matched_keyword": None,
            "service": None,
        }

    keyword_rows = get_cached_service_keywords(clinic_id)

    if not keyword_rows:
        log_timing(
            "Local service resolver",
            resolver_start_ms,
            "status=no_match reason=no_keywords",
        )

        return {
            "status": "no_match",
            "confidence": 0.0,
            "raw_text": raw_text,
            "matched_keyword": None,
            "service": None,
        }

    for row in keyword_rows:
        keyword = row.get("keyword") or ""
        normalized_keyword = normalize_service_text(keyword)
        match_type = row.get("match_type") or "contains"

        if not normalized_keyword:
            continue

        if match_type == "exact":
            matched = normalized_text == normalized_keyword
        else:
            matched = normalized_keyword in normalized_text

        if matched:
            service = build_service_candidate(row)

            log_timing(
                "Local service resolver",
                resolver_start_ms,
                f"status=exact keyword={keyword} service={service.get('service_category_name') if service else None}",
            )

            return {
                "status": "exact",
                "confidence": 0.98,
                "raw_text": raw_text,
                "matched_keyword": keyword,
                "service": service,
            }

    best = None
    second_best = None

    for row in keyword_rows:
        keyword = row.get("keyword") or ""
        normalized_keyword = normalize_service_text(keyword)

        if not normalized_keyword:
            continue

        score_a = fuzz.token_set_ratio(normalized_text, normalized_keyword)
        score_b = fuzz.partial_ratio(normalized_text, normalized_keyword)
        score = max(score_a, score_b)

        candidate = {
            "score": float(score),
            "row": row,
            "keyword": keyword,
        }

        if best is None or candidate["score"] > best["score"]:
            second_best = best
            best = candidate
        elif second_best is None or candidate["score"] > second_best["score"]:
            second_best = candidate

    if not best:
        log_timing(
            "Local service resolver",
            resolver_start_ms,
            "status=no_match reason=no_best",
        )

        return {
            "status": "no_match",
            "confidence": 0.0,
            "raw_text": raw_text,
            "matched_keyword": None,
            "service": None,
        }

    best_score = float(best["score"])
    second_score = float(second_best["score"]) if second_best else 0.0
    score_gap = best_score - second_score

    best_row = best["row"]
    best_keyword = best["keyword"]
    service = build_service_candidate(best_row)

    if best_score >= 90 and score_gap >= 5:
        status = "exact"
        confidence = min(best_score / 100, 0.98)
    elif best_score >= 74 and score_gap >= 4:
        status = "fuzzy_confirm"
        confidence = best_score / 100
    else:
        status = "no_match"
        confidence = best_score / 100

    log_timing(
        "Local service resolver",
        resolver_start_ms,
        (
            f"status={status} score={best_score:.1f} "
            f"second={second_score:.1f} gap={score_gap:.1f} "
            f"keyword={best_keyword} service={service.get('service_category_name') if service else None}"
        ),
    )

    if status == "no_match":
        return {
            "status": "no_match",
            "confidence": confidence,
            "raw_text": raw_text,
            "matched_keyword": best_keyword,
            "service": None,
        }

    return {
        "status": status,
        "confidence": confidence,
        "raw_text": raw_text,
        "matched_keyword": best_keyword,
        "service": service,
    }


def parsed_from_exact_service(service_result: dict, session: dict) -> dict:
    service = service_result.get("service") or {}

    return {
        "intent": "provide_reason",
        "reason": service_result.get("raw_text"),
        "reason_is_specific_enough": True,
        "doctor_name": None,
        "preferred_date_raw": None,
        "date_confirmation": None,
        "slot_choice": None,
        "wants_repeat": False,
        "is_emergency": False,
        "is_unclear": False,
        "language": session.get("language") or "en",
        "confidence": float(service_result.get("confidence") or 0.98),
        "notes": (
            "Matched service locally. "
            f"service={service.get('service_category_name')} "
            f"keyword={service_result.get('matched_keyword')} "
            f"status={service_result.get('status')}"
        ),
    }


def classify_service_menu_option_locally(caller_text: str, session: dict) -> dict | None:
    local_start_ms = now_ms()
    text = normalize_service_text(caller_text)

    if not text:
        return None

    if session.get("current_state") != "service_menu":
        return None

    tooth_pain_terms = [
        "tooth pain",
        "tooth hurts",
        "tooth hurt",
        "my tooth hurts",
        "my tooth hurt",
        "toothache",
        "dental pain",
        "sore tooth",
    ]

    broken_tooth_terms = [
        "broken tooth",
        "tooth broke",
        "my tooth broke",
        "chipped tooth",
        "cracked tooth",
        "fractured tooth",
    ]

    cleaning_terms = [
        "cleaning",
        "teeth cleaning",
        "dental cleaning",
        "hygiene",
    ]

    checkup_terms = [
        "checkup",
        "check up",
        "exam",
        "dental exam",
        "regular checkup",
    ]

    something_else_terms = [
        "something else",
        "other",
        "another thing",
        "different",
        "none of those",
        "not those",
    ]

    def contains_any(terms: list[str]) -> bool:
        return any(term in text for term in terms)

    service_name = None
    canonical_reason = None
    reason_text = None

    if contains_any(tooth_pain_terms):
        service_name = "Tooth Pain"
        canonical_reason = "tooth_pain"
        reason_text = "tooth pain"

    elif contains_any(broken_tooth_terms):
        service_name = "Broken Tooth"
        canonical_reason = "broken_tooth"
        reason_text = "broken tooth"

    elif contains_any(cleaning_terms):
        service_name = "Cleaning"
        canonical_reason = "cleaning"
        reason_text = "cleaning"

    elif contains_any(checkup_terms):
        service_name = "Checkup"
        canonical_reason = "checkup"
        reason_text = "checkup"

    elif contains_any(something_else_terms):
        parsed = {
            "intent": "something_else",
            "reason": caller_text,
            "reason_is_specific_enough": False,
            "doctor_name": None,
            "preferred_date_raw": None,
            "date_confirmation": None,
            "slot_choice": None,
            "wants_repeat": False,
            "is_emergency": False,
            "is_unclear": False,
            "language": session.get("language") or "en",
            "confidence": 0.96,
            "notes": "Caller chose something else from service menu.",
        }

        log_timing(
            "Local classify_service_menu_option_locally",
            local_start_ms,
            "intent=something_else",
        )

        return parsed

    if not service_name:
        log_timing(
            "Local classify_service_menu_option_locally",
            local_start_ms,
            f"no_match text={text}",
        )
        return None

    parsed = {
        "intent": "service_menu_choice",
        "reason": reason_text,
        "reason_is_specific_enough": True,
        "doctor_name": None,
        "preferred_date_raw": None,
        "date_confirmation": None,
        "slot_choice": None,
        "wants_repeat": False,
        "is_emergency": False,
        "is_unclear": False,
        "language": session.get("language") or "en",
        "confidence": 0.98,
        "notes": f"Matched controlled service menu option: {service_name}",
        "service_menu_choice": {
            "service_category_name": service_name,
            "canonical_reason": canonical_reason,
            "reason": reason_text,
        },
    }

    log_timing(
        "Local classify_service_menu_option_locally",
        local_start_ms,
        f"intent=service_menu_choice service={service_name}",
    )

    return parsed


# ---------------------------------------------------------------------
# Cheap AI turn classifier
# ---------------------------------------------------------------------

def safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return "{}"


async def classify_caller_turn_with_openai(
    caller_text: str,
    call_state: dict,
    doctors: list[dict] | None = None,
) -> dict:
    if not openai_client:
        return {
            "intent": "unclear",
            "reason": None,
            "reason_is_specific_enough": False,
            "doctor_name": None,
            "preferred_date_raw": None,
            "date_confirmation": None,
            "slot_choice": None,
            "wants_repeat": False,
            "is_emergency": False,
            "is_unclear": True,
            "language": call_state.get("language") or "en",
            "confidence": 0.0,
            "notes": "OpenAI client is not initialized.",
        }

    doctor_names = []
    for doctor in doctors or []:
        name = doctor.get("display_name") or doctor.get("full_name")
        if name:
            doctor_names.append(name)

    current_state = call_state.get("current_state")
    pending_question = call_state.get("pending_question")
    last_offered_slots = call_state.get("last_offered_slots") or []

    schema = {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": [
                    "provide_reason",
                    "change_reason",
                    "change_date",
                    "confirm_date",
                    "reject_date",
                    "change_doctor",
                    "change_doctor_and_date",
                    "slot_choice",
                    "repeat",
                    "front_desk_followup",
                    "question",
                    "emergency",
                    "goodbye",
                    "unclear",
                ],
            },
            "reason": {"type": ["string", "null"]},
            "reason_is_specific_enough": {"type": "boolean"},
            "doctor_name": {"type": ["string", "null"]},
            "preferred_date_raw": {"type": ["string", "null"]},
            "date_confirmation": {"type": ["boolean", "null"]},
            "slot_choice": {
                "type": ["integer", "null"],
                "description": "1 for first option, 2 for second option, or null.",
            },
            "wants_repeat": {"type": "boolean"},
            "is_emergency": {"type": "boolean"},
            "is_unclear": {"type": "boolean"},
            "language": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "notes": {"type": ["string", "null"]},
        },
        "required": [
            "intent",
            "reason",
            "reason_is_specific_enough",
            "doctor_name",
            "preferred_date_raw",
            "date_confirmation",
            "slot_choice",
            "wants_repeat",
            "is_emergency",
            "is_unclear",
            "language",
            "confidence",
            "notes",
        ],
        "additionalProperties": False,
    }

    system_prompt = (
        "You are a strict turn classifier for a dental clinic AI receptionist. "
        "Classify only the latest caller message into structured JSON. "
        "Do not continue the conversation. Do not invent facts. "
        "Use the current backend state to interpret short answers like yes, no, first, second, or repeat. "
        "\n\n"
        f"Current state: {current_state}\n"
        f"Pending question: {pending_question}\n"
        f"Current known reason: {call_state.get('reason')}\n"
        f"Pending date raw: {call_state.get('pending_date_raw')}\n"
        f"Preferred date raw: {call_state.get('preferred_date_raw')}\n"
        f"Preferred doctor name: {call_state.get('preferred_doctor_name')}\n"
        f"Available doctors: {', '.join(doctor_names) if doctor_names else 'none'}\n"
        f"Last offered slots JSON: {safe_json_dumps(last_offered_slots)}\n"
        "\n"
        "Rules:\n"
        "- If the caller asks to repeat, rephrase, say that again, or asks what you said, intent must be repeat.\n"
        "- Do not treat repeat/rephrase as a date, time, doctor, reason, yes/no, or slot choice.\n"
        "- If the caller says first, second, earlier, later, or a clearly offered time while current_state is slot_choice, classify slot_choice.\n"
        "- If the caller gives a date, classify change_date, not slot_choice.\n"
        "- If the caller gives a doctor, classify change_doctor.\n"
        "- If the caller gives both doctor and date, classify change_doctor_and_date.\n"
        "- If current_state is date_confirmation and caller clearly says yes/correct/yeah/بله/آره/درست/ja/oui, classify confirm_date.\n"
        "- If current_state is date_confirmation and caller clearly says no/nope/نه, classify reject_date.\n"
        "- A vague reason like problem, issue, concern, something wrong, or I need dentist is not specific enough.\n"
        "- Specific reasons include tooth pain, cleaning, checkup, broken tooth, filling, crown, wisdom tooth, bleeding gums, swelling, emergency, orthodontics.\n"
        "- Random foreign fragments, unrelated names, background speech, or garbled text must be unclear.\n"
        "- If caller mentions severe swelling, uncontrolled bleeding, facial trauma, trouble breathing, or major injury, classify emergency.\n"
    )

    try:
        response = await openai_client.responses.create(
            model=OPENAI_EXTRACTION_MODEL,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": caller_text or ""},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "caller_turn_classification",
                    "schema": schema,
                    "strict": True,
                }
            },
        )

        parsed = json.loads(response.output_text)

        if parsed.get("confidence") is None:
            parsed["confidence"] = 0.0

        return parsed

    except Exception as e:
        print(f"Cheap AI classification failed: {e}")
        return {
            "intent": "unclear",
            "reason": None,
            "reason_is_specific_enough": False,
            "doctor_name": None,
            "preferred_date_raw": None,
            "date_confirmation": None,
            "slot_choice": None,
            "wants_repeat": False,
            "is_emergency": False,
            "is_unclear": True,
            "language": call_state.get("language") or "en",
            "confidence": 0.0,
            "notes": f"Classification failed: {e}",
        }


# ---------------------------------------------------------------------
# Backend state machine
# ---------------------------------------------------------------------

def should_trigger_realtime_fallback(
    parsed: dict,
    session: dict,
    next_unclear_count: int,
) -> tuple[bool, str | None]:
    confidence = float(parsed.get("confidence") or 0)

    if parsed.get("intent") == "emergency" and confidence < 0.75:
        return True, "unclear_emergency"

    if confidence < 0.35:
        return True, "very_low_confidence"

    if next_unclear_count >= 3:
        return True, "too_many_unclear_turns"

    return False, None


def get_slot_by_choice(slots: list[dict], choice: int | None) -> dict | None:
    if not slots or not choice:
        return None

    if choice == 1 and len(slots) >= 1:
        return slots[0]

    if choice == 2 and len(slots) >= 2:
        return slots[1]

    return None


def normalize_slots_for_storage(slots: list[dict] | None) -> list[dict]:
    clean_slots = []

    for index, slot in enumerate(slots or [], start=1):
        clean = dict(slot)
        clean["index"] = index
        clean_slots.append(clean)

    return clean_slots


def create_or_update_request_from_session(
    session: dict,
    selected_slot: dict | None = None,
    needs_front_desk_followup: bool = False,
) -> dict | None:
    appointment_request_id = session.get("appointment_request_id")

    if appointment_request_id:
        request_row = {"id": appointment_request_id}
    else:
        request_row = create_appointment_request(
            clinic_id=session.get("clinic_id"),
            call_id=session.get("call_id"),
            patient_phone=session.get("caller_phone"),
            patient_name=None,
            reason=session.get("canonical_reason") or session.get("reason"),
            preferred_time=None,
            urgency=session.get("urgency") or "normal",
            status="new",
            doctor_id=session.get("doctor_id"),
            preferred_doctor_name=session.get("preferred_doctor_name"),
        )

    if not request_row:
        return None

    updates = {
        "preferred_date_raw": session.get("preferred_date_raw"),
        "preferred_date_confirmed": bool(session.get("preferred_date_confirmed")),
        "doctor_id": session.get("doctor_id"),
        "preferred_doctor_name": session.get("preferred_doctor_name"),
        "service_category_id": session.get("service_category_id"),
        "service_category_name": session.get("service_category_name"),
        "duration_minutes": session.get("duration_minutes"),
        "suggested_slots": session.get("last_offered_slots") or [],
        "needs_front_desk_followup": needs_front_desk_followup,
        "slot_selected": bool(selected_slot),
    }

    if selected_slot:
        updates.update(
            {
                "selected_slot_start": selected_slot.get("starts_at"),
                "selected_slot_end": selected_slot.get("ends_at"),
                "preferred_time_raw": selected_slot.get("start_time"),
                "preferred_time_confirmed": True,
            }
        )

    updated = update_appointment_request(request_row["id"], updates)
    return updated or request_row


def build_offer_from_booking_result(
    session: dict,
    booking_result: dict,
) -> dict:
    if not booking_result.get("ok"):
        reason = booking_result.get("reason")

        if reason == "requested_doctor_does_not_provide_service":
            requested = booking_result.get("requested_doctor") or {}
            doctor_name = requested.get("doctor_name") or session.get("preferred_doctor_name")
            response_text = template_doctor_does_not_provide_service(doctor_name)
            return {
                "response_text": response_text,
                "updates": {
                    "current_state": "collect_reason",
                    "pending_question": "reason",
                    "last_message": response_text,
                },
                "action": "doctor_not_eligible",
            }

        if reason == "service_not_matched":
            response_text = template_service_menu_retry()
            return {
                "response_text": response_text,
                "updates": {
                    "current_state": "service_menu",
                    "pending_question": "service_menu",
                    "last_message": response_text,
                },
                "action": "service_not_matched",
            }

        response_text = booking_result.get("message_for_ai") or template_no_slots_found()
        return {
            "response_text": response_text,
            "updates": {
                "current_state": "front_desk_followup",
                "pending_question": None,
                "last_message": response_text,
            },
            "action": "no_booking_options",
        }

    service = booking_result.get("service") or {}
    slots = normalize_slots_for_storage(booking_result.get("slots") or [])
    response_text = format_slot_offer(slots)

    updates = {
        "current_state": "slot_choice",
        "pending_question": "slot_choice",
        "service_category_id": service.get("service_category_id"),
        "service_category_name": service.get("service_name"),
        "canonical_reason": service.get("canonical_reason"),
        "duration_minutes": service.get("duration_minutes") or 30,
        "urgency": service.get("default_urgency") or session.get("urgency") or "normal",
        "last_offered_slots": slots,
        "last_message": response_text,
    }

    doctor_filter = booking_result.get("doctor_filter") or {}
    if doctor_filter.get("doctor_id"):
        updates["doctor_id"] = doctor_filter.get("doctor_id")
        updates["preferred_doctor_name"] = doctor_filter.get("doctor_name")

    return {
        "response_text": response_text,
        "updates": updates,
        "action": "offer_slots",
    }


def handle_state_transition(
    session: dict,
    parsed: dict,
    doctors: list[dict],
) -> dict:
    state_before = session.get("current_state") or "collect_reason"
    intent = parsed.get("intent") or "unclear"

    unclear_count = int(session.get("unclear_count") or 0)

    if intent == "unclear" or parsed.get("is_unclear"):
        unclear_count += 1
    else:
        unclear_count = 0

    fallback_triggered, fallback_reason = should_trigger_realtime_fallback(
        parsed=parsed,
        session=session,
        next_unclear_count=unclear_count,
    )

    if fallback_triggered:
        response_text = "I’m going to connect you to a more flexible assistant now."
        return {
            "response_text": response_text,
            "updates": {
                "current_state": "fallback_realtime",
                "fallback_used": True,
                "fallback_reason": fallback_reason,
                "unclear_count": unclear_count,
                "last_message": response_text,
            },
            "state_after": "fallback_realtime",
            "action": "fallback_realtime",
            "fallback_triggered": True,
            "fallback_reason": fallback_reason,
        }

    if intent == "repeat":
        response_text = session.get("last_message") or template_ask_reason()
        return {
            "response_text": response_text,
            "updates": {
                "last_message": response_text,
                "unclear_count": unclear_count,
            },
            "state_after": state_before,
            "action": "repeat_last_message",
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    if intent == "vague_reason":
        response_text = template_service_menu()

        return {
            "response_text": response_text,
            "updates": {
                "reason": parsed.get("reason"),
                "reason_is_specific_enough": False,
                "current_state": "service_menu",
                "pending_question": "service_menu",
                "last_message": response_text,
                "unclear_count": unclear_count,
            },
            "state_after": "service_menu",
            "action": "ask_service_menu",
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    if state_before == "service_menu":
        if intent == "service_menu_choice":
            choice = parsed.get("service_menu_choice") or {}
            reason = choice.get("reason") or parsed.get("reason")
            service_name = choice.get("service_category_name")
            canonical_reason = choice.get("canonical_reason")

            booking_result = get_booking_options_for_ai(
                clinic_id=session.get("clinic_id"),
                doctors=doctors,
                doctor_name=session.get("preferred_doctor_name"),
                reason=reason,
                preferred_date_raw=session.get("preferred_date_raw"),
                preferred_date_confirmed=bool(session.get("preferred_date_confirmed")),
            )

            session_for_booking = dict(session)
            session_for_booking["reason"] = reason
            session_for_booking["service_category_name"] = service_name
            session_for_booking["canonical_reason"] = canonical_reason

            offer = build_offer_from_booking_result(session_for_booking, booking_result)

            offer["updates"]["reason"] = reason
            offer["updates"]["reason_is_specific_enough"] = True
            offer["updates"]["unclear_count"] = unclear_count

            if service_name:
                offer["updates"]["service_category_name"] = service_name

            if canonical_reason:
                offer["updates"]["canonical_reason"] = canonical_reason

            return {
                "response_text": offer["response_text"],
                "updates": offer["updates"],
                "state_after": offer["updates"].get("current_state", state_before),
                "action": "service_menu_choice_find_slots",
                "fallback_triggered": False,
                "fallback_reason": None,
            }

        if intent == "something_else":
            response_text = "No problem. Please briefly tell me what dental issue you are calling about."

            return {
                "response_text": response_text,
                "updates": {
                    "current_state": "clarify_reason",
                    "pending_question": "specific_reason",
                    "last_message": response_text,
                    "unclear_count": unclear_count,
                },
                "state_after": "clarify_reason",
                "action": "service_menu_something_else",
                "fallback_triggered": False,
                "fallback_reason": None,
            }

        response_text = template_service_menu_retry()

        return {
            "response_text": response_text,
            "updates": {
                "current_state": "service_menu",
                "pending_question": "service_menu",
                "last_message": response_text,
                "unclear_count": unclear_count,
            },
            "state_after": "service_menu",
            "action": "service_menu_retry",
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    if intent == "goodbye":
        response_text = "Thank you for calling. Goodbye."
        return {
            "response_text": response_text,
            "updates": {
                "current_state": "done",
                "pending_question": None,
                "last_message": response_text,
                "unclear_count": unclear_count,
            },
            "state_after": "done",
            "action": "goodbye",
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    if state_before == "confirm_service":
        if intent == "confirm_date":
            reason = session.get("pending_reason_raw") or session.get("pending_canonical_reason")

            session_for_booking = dict(session)
            session_for_booking["reason"] = reason
            session_for_booking["service_category_id"] = session.get("pending_service_category_id")
            session_for_booking["service_category_name"] = session.get("pending_service_category_name")
            session_for_booking["canonical_reason"] = session.get("pending_canonical_reason")
            session_for_booking["duration_minutes"] = session.get("pending_duration_minutes")

            booking_result = get_booking_options_for_ai(
                clinic_id=session.get("clinic_id"),
                doctors=doctors,
                doctor_name=session.get("preferred_doctor_name"),
                reason=reason,
                preferred_date_raw=session.get("preferred_date_raw"),
                preferred_date_confirmed=bool(session.get("preferred_date_confirmed")),
            )

            offer = build_offer_from_booking_result(session_for_booking, booking_result)

            offer["updates"].update(
                {
                    "reason": reason,
                    "reason_is_specific_enough": True,
                    "service_category_id": session.get("pending_service_category_id"),
                    "service_category_name": session.get("pending_service_category_name"),
                    "canonical_reason": session.get("pending_canonical_reason"),
                    "duration_minutes": session.get("pending_duration_minutes"),
                    "pending_service_category_id": None,
                    "pending_service_category_name": None,
                    "pending_canonical_reason": None,
                    "pending_duration_minutes": None,
                    "pending_reason_raw": None,
                    "pending_service_confidence": None,
                    "pending_service_matched_keyword": None,
                    "unclear_count": unclear_count,
                }
            )

            return {
                "response_text": offer["response_text"],
                "updates": offer["updates"],
                "state_after": offer["updates"].get("current_state", state_before),
                "action": "service_confirmed_find_slots",
                "fallback_triggered": False,
                "fallback_reason": None,
            }

        if intent == "reject_date":
            response_text = template_service_menu_retry()

            return {
                "response_text": response_text,
                "updates": {
                    "current_state": "service_menu",
                    "pending_question": "service_menu",
                    "pending_service_category_id": None,
                    "pending_service_category_name": None,
                    "pending_canonical_reason": None,
                    "pending_duration_minutes": None,
                    "pending_reason_raw": None,
                    "pending_service_confidence": None,
                    "pending_service_matched_keyword": None,
                    "last_message": response_text,
                    "unclear_count": unclear_count,
                },
                "state_after": "service_menu",
                "action": "service_rejected_back_to_menu",
                "fallback_triggered": False,
                "fallback_reason": None,
            }

        response_text = session.get("last_message") or template_confirm_service(
            session.get("pending_service_category_name")
        )

        return {
            "response_text": response_text,
            "updates": {
                "last_message": response_text,
                "unclear_count": unclear_count,
            },
            "state_after": "confirm_service",
            "action": "repeat_service_confirmation",
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    if intent == "emergency" or parsed.get("is_emergency"):
        response_text = template_emergency()
        return {
            "response_text": response_text,
            "updates": {
                "current_state": "front_desk_followup",
                "pending_question": None,
                "urgency": "urgent",
                "last_message": response_text,
                "unclear_count": unclear_count,
            },
            "state_after": "front_desk_followup",
            "action": "emergency_guidance",
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    if intent == "front_desk_followup":
        request_row = create_or_update_request_from_session(
            session,
            selected_slot=None,
            needs_front_desk_followup=True,
        )
        response_text = template_front_desk_followup()
        updates = {
            "current_state": "done",
            "pending_question": None,
            "last_message": response_text,
            "unclear_count": unclear_count,
        }
        if request_row:
            updates["appointment_request_id"] = request_row.get("id")

        return {
            "response_text": response_text,
            "updates": updates,
            "state_after": "done",
            "action": "front_desk_followup",
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    if intent in ["change_date", "change_doctor_and_date"]:
        preferred_date_raw = parsed.get("preferred_date_raw")
        doctor_name = parsed.get("doctor_name")

        updates = {
            "pending_date_raw": preferred_date_raw,
            "preferred_date_confirmed": False,
            "current_state": "date_confirmation",
            "pending_question": "date_confirmation",
            "unclear_count": unclear_count,
        }

        if doctor_name:
            matched_doctor = match_doctor_from_name(doctors, doctor_name)
            if matched_doctor:
                updates["doctor_id"] = matched_doctor.get("id")
                updates["preferred_doctor_name"] = (
                    matched_doctor.get("display_name")
                    or matched_doctor.get("full_name")
                    or doctor_name
                )
            else:
                updates["preferred_doctor_name"] = doctor_name

        if preferred_date_raw:
            response_text = template_confirm_date(preferred_date_raw)
        else:
            response_text = template_ask_date()
            updates["current_state"] = "collect_reason"
            updates["pending_question"] = "date"

        updates["last_message"] = response_text

        return {
            "response_text": response_text,
            "updates": updates,
            "state_after": updates["current_state"],
            "action": "confirm_new_date",
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    if intent == "change_doctor":
        doctor_name = parsed.get("doctor_name")
        matched_doctor = match_doctor_from_name(doctors, doctor_name)

        if not matched_doctor:
            response_text = template_doctor_not_found(doctor_name)
            return {
                "response_text": response_text,
                "updates": {
                    "preferred_doctor_name": doctor_name,
                    "last_message": response_text,
                    "unclear_count": unclear_count,
                },
                "state_after": state_before,
                "action": "doctor_not_found",
                "fallback_triggered": False,
                "fallback_reason": None,
            }

        preferred_doctor_name = (
            matched_doctor.get("display_name")
            or matched_doctor.get("full_name")
            or doctor_name
        )

        session_for_booking = dict(session)
        session_for_booking["doctor_id"] = matched_doctor.get("id")
        session_for_booking["preferred_doctor_name"] = preferred_doctor_name

        reason = session_for_booking.get("reason") or session_for_booking.get("canonical_reason")

        if not reason:
            response_text = template_ask_reason()
            return {
                "response_text": response_text,
                "updates": {
                    "doctor_id": matched_doctor.get("id"),
                    "preferred_doctor_name": preferred_doctor_name,
                    "current_state": "collect_reason",
                    "pending_question": "reason",
                    "last_message": response_text,
                    "unclear_count": unclear_count,
                },
                "state_after": "collect_reason",
                "action": "doctor_saved_ask_reason",
                "fallback_triggered": False,
                "fallback_reason": None,
            }

        booking_result = get_booking_options_for_ai(
            clinic_id=session.get("clinic_id"),
            doctors=doctors,
            doctor_name=preferred_doctor_name,
            reason=reason,
            preferred_date_raw=session.get("preferred_date_raw"),
            preferred_date_confirmed=bool(session.get("preferred_date_confirmed")),
        )

        offer = build_offer_from_booking_result(session_for_booking, booking_result)
        offer["updates"]["doctor_id"] = matched_doctor.get("id")
        offer["updates"]["preferred_doctor_name"] = preferred_doctor_name
        offer["updates"]["unclear_count"] = unclear_count

        return {
            "response_text": offer["response_text"],
            "updates": offer["updates"],
            "state_after": offer["updates"].get("current_state", state_before),
            "action": offer["action"],
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    if state_before == "date_confirmation":
        if intent == "confirm_date":
            pending_date_raw = session.get("pending_date_raw")

            session_for_booking = dict(session)
            session_for_booking["preferred_date_raw"] = pending_date_raw
            session_for_booking["preferred_date_confirmed"] = True

            reason = session.get("reason") or session.get("canonical_reason")

            if not reason:
                response_text = template_ask_reason()
                return {
                    "response_text": response_text,
                    "updates": {
                        "preferred_date_raw": pending_date_raw,
                        "preferred_date_confirmed": True,
                        "pending_date_raw": None,
                        "current_state": "collect_reason",
                        "pending_question": "reason",
                        "last_message": response_text,
                        "unclear_count": unclear_count,
                    },
                    "state_after": "collect_reason",
                    "action": "date_confirmed_ask_reason",
                    "fallback_triggered": False,
                    "fallback_reason": None,
                }

            booking_result = get_booking_options_for_ai(
                clinic_id=session.get("clinic_id"),
                doctors=doctors,
                doctor_name=session.get("preferred_doctor_name"),
                reason=reason,
                preferred_date_raw=pending_date_raw,
                preferred_date_confirmed=True,
            )

            offer = build_offer_from_booking_result(session_for_booking, booking_result)
            offer["updates"]["preferred_date_raw"] = pending_date_raw
            offer["updates"]["preferred_date_confirmed"] = True
            offer["updates"]["pending_date_raw"] = None
            offer["updates"]["unclear_count"] = unclear_count

            return {
                "response_text": offer["response_text"],
                "updates": offer["updates"],
                "state_after": offer["updates"].get("current_state", state_before),
                "action": "date_confirmed_find_slots",
                "fallback_triggered": False,
                "fallback_reason": None,
            }

        if intent == "reject_date":
            response_text = template_ask_date()
            return {
                "response_text": response_text,
                "updates": {
                    "pending_date_raw": None,
                    "preferred_date_raw": None,
                    "preferred_date_confirmed": False,
                    "current_state": "collect_reason",
                    "pending_question": "date",
                    "last_message": response_text,
                    "unclear_count": unclear_count,
                },
                "state_after": "collect_reason",
                "action": "date_rejected",
                "fallback_triggered": False,
                "fallback_reason": None,
            }

        response_text = session.get("last_message") or template_confirm_date(
            session.get("pending_date_raw") or "that date"
        )

        return {
            "response_text": response_text,
            "updates": {
                "last_message": response_text,
                "unclear_count": unclear_count,
            },
            "state_after": "date_confirmation",
            "action": "repeat_date_confirmation",
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    if state_before == "slot_choice":
        if intent == "slot_choice":
            selected_slot = get_slot_by_choice(
                session.get("last_offered_slots") or [],
                parsed.get("slot_choice"),
            )

            if not selected_slot:
                response_text = template_ask_slot_choice_again()
                return {
                    "response_text": response_text,
                    "updates": {
                        "last_message": response_text,
                        "unclear_count": unclear_count,
                    },
                    "state_after": "slot_choice",
                    "action": "ask_slot_choice_again",
                    "fallback_triggered": False,
                    "fallback_reason": None,
                }

            request_row = create_or_update_request_from_session(
                session,
                selected_slot=selected_slot,
                needs_front_desk_followup=False,
            )

            response_text = template_final_noted(selected_slot)

            updates = {
                "current_state": "done",
                "pending_question": None,
                "selected_slot": selected_slot,
                "last_message": response_text,
                "unclear_count": unclear_count,
            }

            if request_row:
                updates["appointment_request_id"] = request_row.get("id")

            return {
                "response_text": response_text,
                "updates": updates,
                "state_after": "done",
                "action": "slot_selected_save_request",
                "fallback_triggered": False,
                "fallback_reason": None,
            }

        response_text = template_ask_slot_choice_again()
        return {
            "response_text": response_text,
            "updates": {
                "last_message": response_text,
                "unclear_count": unclear_count,
            },
            "state_after": "slot_choice",
            "action": "unclear_slot_choice",
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    if intent in ["provide_reason", "change_reason"]:
        reason = parsed.get("reason")

        if not parsed.get("reason_is_specific_enough"):
            response_text = template_service_menu()
            return {
                "response_text": response_text,
                "updates": {
                    "reason": reason,
                    "reason_is_specific_enough": False,
                    "current_state": "service_menu",
                    "pending_question": "service_menu",
                    "last_message": response_text,
                    "unclear_count": unclear_count,
                },
                "state_after": "service_menu",
                "action": "ask_service_menu_from_vague_reason",
                "fallback_triggered": False,
                "fallback_reason": None,
            }

        booking_result = get_booking_options_for_ai(
            clinic_id=session.get("clinic_id"),
            doctors=doctors,
            doctor_name=session.get("preferred_doctor_name"),
            reason=reason,
            preferred_date_raw=session.get("preferred_date_raw"),
            preferred_date_confirmed=bool(session.get("preferred_date_confirmed")),
        )

        session_for_booking = dict(session)
        session_for_booking["reason"] = reason

        offer = build_offer_from_booking_result(session_for_booking, booking_result)
        offer["updates"]["reason"] = reason
        offer["updates"]["reason_is_specific_enough"] = True
        offer["updates"]["unclear_count"] = unclear_count

        return {
            "response_text": offer["response_text"],
            "updates": offer["updates"],
            "state_after": offer["updates"].get("current_state", state_before),
            "action": offer["action"],
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    response_text = template_ask_reason()
    return {
        "response_text": response_text,
        "updates": {
            "current_state": "collect_reason",
            "pending_question": "reason",
            "last_message": response_text,
            "unclear_count": unclear_count,
        },
        "state_after": "collect_reason",
        "action": "default_ask_reason",
        "fallback_triggered": False,
        "fallback_reason": None,
    }


# ---------------------------------------------------------------------
# Stateful low-cost Twilio flow
# ---------------------------------------------------------------------

@app.post("/twilio/voice")
async def twilio_voice(request: Request):
    request_start_ms = now_ms()
    print("[TIMING] /twilio/voice received | routing_to=realtime")

    form = await request.form()

    caller = normalize_phone(form.get("From"))
    to_number = normalize_phone(form.get("To"))
    call_sid = form.get("CallSid") or ""

    print(
        f"[VOICE_START_REALTIME] call_sid={call_sid} "
        f"from={caller} to={to_number}"
    )

    log_timing(
        "TOTAL /twilio/voice",
        request_start_ms,
        f"return=realtime call_sid={call_sid}",
    )

    return twiml_connect_realtime(
        caller_phone=caller,
        to_number=to_number,
        call_sid=call_sid,
        intro_message="Hi, thanks for calling Westview Dental.",
    )


@app.post("/twilio/voice-stateful")
async def twilio_voice_stateful(request: Request):
    request_start_ms = now_ms()
    print("[TIMING] /twilio/voice-stateful received")

    form = await request.form()

    caller = normalize_phone(form.get("From"))
    to_number = normalize_phone(form.get("To"))
    call_sid = form.get("CallSid") or ""

    print(
        f"[VOICE_START] call_sid={call_sid} "
        f"from={caller} to={to_number}"
    )

    clinic_lookup_start_ms = now_ms()
    clinic = find_clinic_by_twilio_number(to_number)
    clinic_id = clinic["id"] if clinic else None
    log_timing(
        "Supabase find_clinic_by_twilio_number",
        clinic_lookup_start_ms,
        f"clinic_found={bool(clinic)} clinic_id={clinic_id}",
    )

    save_call_start_ms = now_ms()
    saved_call = save_call_to_db(
        clinic_id=clinic_id,
        twilio_call_sid=call_sid,
        caller_phone=caller,
        speech_result="",
        confidence=None,
        intent="stateful",
        urgency="normal",
        summary="Stateful AI call started.",
    )
    log_timing(
        "Supabase save_call_to_db",
        save_call_start_ms,
        f"call_saved={bool(saved_call)}",
    )

    call_id = saved_call["id"] if saved_call else None

    session_lookup_start_ms = now_ms()
    existing_session = get_call_session_by_twilio_sid(call_sid)
    log_timing(
        "Supabase get_call_session_by_twilio_sid on voice start",
        session_lookup_start_ms,
        f"found={bool(existing_session)} call_sid={call_sid}",
    )

    if not existing_session:
        create_session_start_ms = now_ms()
        call_session = create_call_session(
            clinic_id=clinic_id,
            call_id=call_id,
            twilio_call_sid=call_sid,
            caller_phone=caller,
            current_state="collect_reason",
            pending_question="reason",
            language="en",
        )
        log_timing(
            "Supabase create_call_session",
            create_session_start_ms,
            f"session_created={bool(call_session)}",
        )
    else:
        call_session = existing_session

    greeting = template_greeting()

    if call_session:
        update_session_start_ms = now_ms()
        update_call_session(
            call_session["id"],
            {
                "last_message": greeting,
                "current_state": "collect_reason",
                "pending_question": "reason",
            },
        )
        log_timing("Supabase update_call_session greeting", update_session_start_ms)

        save_log_start_ms = now_ms()
        save_call_turn_log(
            call_session_id=call_session["id"],
            call_id=call_id,
            twilio_call_sid=call_sid,
            role="assistant",
            raw_text=greeting,
            parsed_intent=None,
            parsed_entities={},
            confidence=None,
            state_before=None,
            state_after="collect_reason",
            backend_action="greeting",
            backend_response=greeting,
        )
        log_timing("Supabase save greeting call_turn_log", save_log_start_ms)

    action_url = f"{PUBLIC_BASE_URL}/twilio/stateful-turn"

    log_timing(
        "TOTAL /twilio/voice-stateful",
        request_start_ms,
        f"call_sid={call_sid} action_url={action_url}",
    )

    return twiml_gather(
        message=greeting,
        action_url=action_url,
        language="en-US",
    )


@app.post("/twilio/stateful-turn")
async def twilio_stateful_turn(request: Request):
    request_start_ms = now_ms()
    print("[TIMING] /twilio/stateful-turn received")

    form_start_ms = now_ms()
    form = await request.form()
    log_timing("FastAPI parse request.form", form_start_ms)

    caller_text = str(form.get("SpeechResult") or "").strip()
    confidence = str(form.get("Confidence") or "")
    caller = normalize_phone(form.get("From"))
    to_number = normalize_phone(form.get("To"))
    call_sid = form.get("CallSid") or ""

    print(
        f"[TURN] call_sid={call_sid} "
        f"from={caller} to={to_number} "
        f"speech='{caller_text}' "
        f"twilio_confidence={confidence}"
    )

    action_url = f"{PUBLIC_BASE_URL}/twilio/stateful-turn"

    session_lookup_start_ms = now_ms()
    session = get_call_session_by_twilio_sid(call_sid)
    log_timing(
        "Supabase get_call_session_by_twilio_sid",
        session_lookup_start_ms,
        f"found={bool(session)} call_sid={call_sid}",
    )

    if not session:
        recovery_start_ms = now_ms()

        clinic = find_clinic_by_twilio_number(to_number)
        clinic_id = clinic["id"] if clinic else None

        saved_call = save_call_to_db(
            clinic_id=clinic_id,
            twilio_call_sid=call_sid,
            caller_phone=caller,
            speech_result=caller_text,
            confidence=confidence,
            intent="stateful",
            urgency="normal",
            summary="Stateful AI call recovered without session.",
        )

        session = create_call_session(
            clinic_id=clinic_id,
            call_id=saved_call["id"] if saved_call else None,
            twilio_call_sid=call_sid,
            caller_phone=caller,
            current_state="collect_reason",
            pending_question="reason",
            language="en",
        )

        log_timing(
            "Recovery create_call_session path",
            recovery_start_ms,
            f"session_created={bool(session)} clinic_id={clinic_id}",
        )

    if not session:
        log_timing(
            "TOTAL /twilio/stateful-turn",
            request_start_ms,
            "return=fallback_no_session",
        )

        return twiml_connect_realtime(
            caller_phone=caller,
            to_number=to_number,
            call_sid=call_sid,
            intro_message="I’m having trouble loading the call. I’ll connect you to the AI receptionist now.",
        )

    state_before = session.get("current_state") or "collect_reason"

    if not caller_text:
        response_text = session.get("last_message") or template_ask_reason()

        save_empty_log_start_ms = now_ms()
        save_call_turn_log(
            call_session_id=session.get("id"),
            call_id=session.get("call_id"),
            twilio_call_sid=call_sid,
            role="caller",
            raw_text="",
            parsed_intent="unclear",
            parsed_entities={},
            confidence=0.0,
            state_before=state_before,
            state_after=state_before,
            backend_action="empty_speech_repeat_last",
            backend_response=response_text,
        )
        log_timing("Supabase save empty speech log", save_empty_log_start_ms)

        log_timing(
            "TOTAL /twilio/stateful-turn",
            request_start_ms,
            "return=empty_speech_repeat_last",
        )

        return twiml_gather(
            message=response_text,
            action_url=action_url,
            language="en-US",
        )

    update_call_start_ms = now_ms()
    update_call(
        session.get("call_id"),
        {
            "speech_result": f"Caller: {caller_text}",
            "confidence": confidence,
        },
    )
    log_timing("Supabase update_call transcript", update_call_start_ms)

    doctors_start_ms = now_ms()
    doctors = get_active_doctors_for_clinic(session.get("clinic_id"))
    log_timing(
        "Supabase get_active_doctors_for_clinic",
        doctors_start_ms,
        f"doctor_count={len(doctors)}",
    )

    transition = None

    local_classifier_start_ms = now_ms()

    parsed = classify_simple_turn_locally(caller_text, session)

    if not parsed:
        parsed = classify_service_menu_option_locally(caller_text, session)

    service_resolution = None

    # Important:
    # If we are inside service_menu and the controlled menu parser failed,
    # do not guess with fuzzy/OpenAI. Let state machine repeat controlled options.
    if not parsed and session.get("current_state") == "service_menu":
        parsed = {
            "intent": "unclear",
            "reason": None,
            "reason_is_specific_enough": False,
            "doctor_name": None,
            "preferred_date_raw": None,
            "date_confirmation": None,
            "slot_choice": None,
            "wants_repeat": False,
            "is_emergency": False,
            "is_unclear": True,
            "language": session.get("language") or "en",
            "confidence": 0.6,
            "notes": "Unclear response to controlled service menu.",
        }

    if not parsed:
        service_resolution = resolve_service_locally(
            caller_text=caller_text,
            clinic_id=session.get("clinic_id"),
        )

        if service_resolution.get("status") == "exact":
            parsed = parsed_from_exact_service(service_resolution, session)

        elif service_resolution.get("status") == "fuzzy_confirm":
            service = service_resolution.get("service") or {}
            response_text = template_confirm_service(service.get("service_category_name"))

            transition = {
                "response_text": response_text,
                "updates": {
                    "current_state": "confirm_service",
                    "pending_question": "service_confirmation",
                    "pending_service_category_id": service.get("service_category_id"),
                    "pending_service_category_name": service.get("service_category_name"),
                    "pending_canonical_reason": service.get("canonical_reason"),
                    "pending_duration_minutes": service.get("duration_minutes"),
                    "pending_reason_raw": service_resolution.get("raw_text"),
                    "pending_service_confidence": service_resolution.get("confidence"),
                    "pending_service_matched_keyword": service_resolution.get("matched_keyword"),
                    "last_message": response_text,
                    "unclear_count": 0,
                },
                "state_after": "confirm_service",
                "action": "confirm_fuzzy_service",
                "fallback_triggered": False,
                "fallback_reason": None,
            }

            parsed = {
                "intent": "provide_reason",
                "reason": service_resolution.get("raw_text"),
                "reason_is_specific_enough": False,
                "doctor_name": None,
                "preferred_date_raw": None,
                "date_confirmation": None,
                "slot_choice": None,
                "wants_repeat": False,
                "is_emergency": False,
                "is_unclear": False,
                "language": session.get("language") or "en",
                "confidence": float(service_resolution.get("confidence") or 0.75),
                "notes": (
                    "Fuzzy service match requires confirmation. "
                    f"service={service.get('service_category_name')} "
                    f"keyword={service_resolution.get('matched_keyword')}"
                ),
            }

    log_timing(
        "Local parser total decision",
        local_classifier_start_ms,
        f"matched={bool(parsed)} service_status={service_resolution.get('status') if service_resolution else None}",
    )

    if not parsed:
        classifier_start_ms = now_ms()
        parsed = await classify_caller_turn_with_openai(
            caller_text=caller_text,
            call_state=session,
            doctors=doctors,
        )
        log_timing(
            "OpenAI classify_caller_turn_with_openai",
            classifier_start_ms,
            f"intent={parsed.get('intent')} confidence={parsed.get('confidence')}",
        )
    else:
        print(
            f"[LOCAL_PARSER] used local parser "
            f"intent={parsed.get('intent')} "
            f"confidence={parsed.get('confidence')}"
        )

    if transition is None:
        transition_start_ms = now_ms()
        transition = handle_state_transition(
            session=session,
            parsed=parsed,
            doctors=doctors,
        )
        log_timing(
            "Backend handle_state_transition",
            transition_start_ms,
            f"action={transition.get('action')} state_after={transition.get('state_after')}",
        )
    else:
        print(
            f"[STATE_MACHINE] using prebuilt transition "
            f"action={transition.get('action')} "
            f"state_after={transition.get('state_after')}"
        )

    updates = transition.get("updates") or {}
    response_text = transition.get("response_text") or template_ask_reason()
    state_after = transition.get("state_after") or updates.get("current_state") or state_before

    update_session_start_ms = now_ms()
    updated_session = update_call_session(
        session["id"],
        updates,
    )
    log_timing(
        "Supabase update_call_session",
        update_session_start_ms,
        f"updated={bool(updated_session)}",
    )

    save_logs_start_ms = now_ms()

    save_call_turn_log(
        call_session_id=session.get("id"),
        call_id=session.get("call_id"),
        twilio_call_sid=call_sid,
        role="caller",
        raw_text=caller_text,
        cleaned_text=caller_text,
        parsed_intent=parsed.get("intent"),
        parsed_entities=parsed,
        confidence=parsed.get("confidence"),
        state_before=state_before,
        state_after=state_after,
        backend_action=transition.get("action"),
        backend_response=response_text,
        fallback_triggered=bool(transition.get("fallback_triggered")),
        fallback_reason=transition.get("fallback_reason"),
    )

    save_call_turn_log(
        call_session_id=session.get("id"),
        call_id=session.get("call_id"),
        twilio_call_sid=call_sid,
        role="assistant",
        raw_text=response_text,
        parsed_intent=None,
        parsed_entities={},
        confidence=None,
        state_before=state_before,
        state_after=state_after,
        backend_action=transition.get("action"),
        backend_response=response_text,
        fallback_triggered=bool(transition.get("fallback_triggered")),
        fallback_reason=transition.get("fallback_reason"),
    )

    log_timing("Supabase save_call_turn_logs", save_logs_start_ms)

    update_summary_start_ms = now_ms()
    update_call(
        session.get("call_id"),
        {
            "summary": f"Stateful call state: {state_after}. Last action: {transition.get('action')}.",
        },
    )
    log_timing("Supabase update_call summary", update_summary_start_ms)

    if transition.get("fallback_triggered"):
        log_timing(
            "TOTAL /twilio/stateful-turn",
            request_start_ms,
            "return=fallback_realtime",
        )

        return twiml_connect_realtime(
            caller_phone=caller,
            to_number=to_number,
            call_sid=call_sid,
            intro_message=response_text,
        )

    if state_after == "done":
        log_timing(
            "TOTAL /twilio/stateful-turn",
            request_start_ms,
            "return=say_and_hangup",
        )

        return twiml_say_and_hangup(response_text)

    log_timing(
        "TOTAL /twilio/stateful-turn",
        request_start_ms,
        "return=gather",
    )

    return twiml_gather(
        message=response_text,
        action_url=action_url,
        language="en-US",
    )


# ---------------------------------------------------------------------
# Health/debug endpoints
# ---------------------------------------------------------------------

@app.get("/")
def health_check():
    parsed = urlparse(SUPABASE_URL) if SUPABASE_URL else None

    return {
        "status": "ok",
        "service": "dental-ai-receptionist",
        "supabase_connected": supabase is not None,
        "has_supabase_url": bool(SUPABASE_URL),
        "has_service_role_key": bool(SUPABASE_SERVICE_ROLE_KEY),
        "supabase_url_preview": SUPABASE_URL[:30] if SUPABASE_URL else None,
        "supabase_hostname": parsed.hostname if parsed else None,
        "mode": "backend_state_machine_with_realtime_fallback",
    }


@app.get("/debug/supabase-test")
def debug_supabase_test():
    parsed = urlparse(SUPABASE_URL) if SUPABASE_URL else None

    if not supabase:
        return {
            "ok": False,
            "error": "Supabase client is not initialized",
            "has_supabase_url": bool(SUPABASE_URL),
            "has_service_role_key": bool(SUPABASE_SERVICE_ROLE_KEY),
            "supabase_url": SUPABASE_URL,
            "hostname": parsed.hostname if parsed else None,
        }

    try:
        result = (
            supabase.table("clinics")
            .select("id,name,phone_number")
            .limit(5)
            .execute()
        )

        return {
            "ok": True,
            "supabase_url": SUPABASE_URL,
            "hostname": parsed.hostname if parsed else None,
            "data": result.data,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "supabase_url": SUPABASE_URL,
            "hostname": parsed.hostname if parsed else None,
        }


@app.get("/debug/booking-options")
def debug_booking_options(
    clinic_id: str,
    doctor_name: str | None = None,
    reason: str = "tooth pain",
    preferred_date_raw: str | None = None,
    preferred_date_confirmed: bool = False,
):
    try:
        doctors = get_active_doctors_for_clinic(clinic_id)

        result = get_booking_options_for_ai(
            clinic_id=clinic_id,
            doctors=doctors,
            doctor_name=doctor_name,
            reason=reason,
            preferred_date_raw=preferred_date_raw,
            preferred_date_confirmed=preferred_date_confirmed,
        )

        return {
            "ok": True,
            "doctors_loaded": doctors,
            "booking_result": result,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }


# ---------------------------------------------------------------------
# Old simple speech endpoint kept for safety/testing
# ---------------------------------------------------------------------

def detect_intent_and_urgency(text: str) -> tuple[str, str]:
    lower_text = text.lower()

    if any(
        word in lower_text
        for word in [
            "pain",
            "swelling",
            "bleeding",
            "emergency",
            "urgent",
            "broken tooth",
            "infection",
            "abscess",
        ]
    ):
        return "urgent", "urgent"

    if any(
        word in lower_text
        for word in ["appointment", "book", "schedule", "cleaning", "checkup", "exam"]
    ):
        return "appointment", "normal"

    if any(
        word in lower_text
        for word in ["hour", "hours", "open", "location", "address"]
    ):
        return "hours_location", "normal"

    return "general", "normal"


@app.post("/twilio/speech")
async def twilio_speech(request: Request):
    form = await request.form()

    speech_result = form.get("SpeechResult", "")
    confidence = form.get("Confidence", "")
    caller = normalize_phone(form.get("From"))
    to_number = normalize_phone(form.get("To"))
    call_sid = form.get("CallSid")

    intent, urgency = detect_intent_and_urgency(speech_result)

    clinic = find_clinic_by_twilio_number(to_number)
    clinic_id = clinic["id"] if clinic else None

    summary = f"Caller said: {speech_result}. Intent: {intent}. Urgency: {urgency}."

    saved_call = save_call_to_db(
        clinic_id=clinic_id,
        twilio_call_sid=call_sid,
        caller_phone=caller,
        speech_result=speech_result,
        confidence=confidence,
        intent=intent,
        urgency=urgency,
        summary=summary,
    )

    call_id = saved_call["id"] if saved_call else None

    if intent == "appointment":
        appointment_request = create_appointment_request(
            clinic_id=clinic_id,
            call_id=call_id,
            patient_phone=caller,
            reason=speech_result,
            urgency=urgency,
        )

        if appointment_request:
            return twiml_say_and_hangup(
                "Thank you. I captured your request and the front desk will contact you to confirm."
            )

    elif intent == "hours_location":
        return twiml_say_and_hangup(
            "Westview Dental is open Monday to Friday from 9 AM to 5 PM. "
            "The clinic is located in Vancouver, British Columbia."
        )

    elif intent == "urgent":
        return twiml_say_and_hangup(
            "I am sorry you are dealing with that. "
            "If you are experiencing severe swelling, uncontrolled bleeding, facial trauma, or trouble breathing, "
            "please seek emergency medical care immediately. "
            "I will mark this as urgent for the clinic team."
        )

    return twiml_say_and_hangup(
        "Thank you. I captured your message. I will send this to the front desk for follow up."
    )