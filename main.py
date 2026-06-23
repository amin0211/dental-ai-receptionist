import os
from urllib.parse import urlparse
import json
import asyncio
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from supabase import create_client, Client
from openai import AsyncOpenAI
import websockets

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
)

app = FastAPI()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_REALTIME_MODEL = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2")
OPENAI_EXTRACTION_MODEL = os.environ.get("OPENAI_EXTRACTION_MODEL", "gpt-4.1-mini")

PUBLIC_BASE_URL = os.environ.get(
    "PUBLIC_BASE_URL",
    "https://web-production-18008.up.railway.app",
).rstrip("/")

PUBLIC_WS_URL = os.environ.get(
    "PUBLIC_WS_URL",
    "wss://web-production-18008.up.railway.app",
).rstrip("/")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


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


def format_slot_display_fallback(slot: dict) -> str:
    doctor_name = slot.get("doctor_name") or "the dentist"
    date_text = slot.get("date") or ""
    start_time = slot.get("start_time") or ""
    return f"{doctor_name} on {date_text} at {start_time}".strip()


def template_final_noted(slot: dict) -> str:
    display = slot.get("display") or format_slot_display_fallback(slot)
    return (
        f"I’ve noted your request for {display}. "
        "The front desk will contact you to confirm."
    )


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
            "reason": {
                "type": ["string", "null"],
            },
            "reason_is_specific_enough": {
                "type": "boolean",
            },
            "doctor_name": {
                "type": ["string", "null"],
            },
            "preferred_date_raw": {
                "type": ["string", "null"],
            },
            "date_confirmation": {
                "type": ["boolean", "null"],
            },
            "slot_choice": {
                "type": ["integer", "null"],
                "description": "1 for first option, 2 for second option, or null.",
            },
            "wants_repeat": {
                "type": "boolean",
            },
            "is_emergency": {
                "type": "boolean",
            },
            "is_unclear": {
                "type": "boolean",
            },
            "language": {
                "type": ["string", "null"],
            },
            "confidence": {
                "type": "number",
            },
            "notes": {
                "type": ["string", "null"],
            },
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
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": caller_text or "",
                },
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
            response_text = template_clarify_reason()
            return {
                "response_text": response_text,
                "updates": {
                    "current_state": "clarify_reason",
                    "pending_question": "specific_reason",
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
    confidence = float(parsed.get("confidence") or 0)

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

    if intent == "emergency" or parsed.get("is_emergency"):
        response_text = template_emergency()
        return {
            "response_text": response_text,
            "updates": {
                "current_state": "front_desk_followup",
                "pending_question": None,
                "urgency": "urgent",
                "needs_front_desk_followup": True,
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
            response_text = template_clarify_reason()
            return {
                "response_text": response_text,
                "updates": {
                    "reason": reason,
                    "reason_is_specific_enough": False,
                    "current_state": "clarify_reason",
                    "pending_question": "specific_reason",
                    "last_message": response_text,
                    "unclear_count": unclear_count,
                },
                "state_after": "clarify_reason",
                "action": "clarify_vague_reason",
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
    return await twilio_voice_stateful(request)


@app.post("/twilio/voice-stateful")
async def twilio_voice_stateful(request: Request):
    form = await request.form()

    caller = normalize_phone(form.get("From"))
    to_number = normalize_phone(form.get("To"))
    call_sid = form.get("CallSid") or ""

    clinic = find_clinic_by_twilio_number(to_number)
    clinic_id = clinic["id"] if clinic else None

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

    call_id = saved_call["id"] if saved_call else None

    existing_session = get_call_session_by_twilio_sid(call_sid)

    if not existing_session:
        call_session = create_call_session(
            clinic_id=clinic_id,
            call_id=call_id,
            twilio_call_sid=call_sid,
            caller_phone=caller,
            current_state="collect_reason",
            pending_question="reason",
            language="en",
        )
    else:
        call_session = existing_session

    greeting = template_greeting()

    if call_session:
        update_call_session(
            call_session["id"],
            {
                "last_message": greeting,
                "current_state": "collect_reason",
                "pending_question": "reason",
            },
        )

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

    action_url = f"{PUBLIC_BASE_URL}/twilio/stateful-turn"

    return twiml_gather(
        message=greeting,
        action_url=action_url,
        language="en-US",
    )


@app.post("/twilio/stateful-turn")
async def twilio_stateful_turn(request: Request):
    form = await request.form()

    caller_text = str(form.get("SpeechResult") or "").strip()
    confidence = str(form.get("Confidence") or "")
    caller = normalize_phone(form.get("From"))
    to_number = normalize_phone(form.get("To"))
    call_sid = form.get("CallSid") or ""

    action_url = f"{PUBLIC_BASE_URL}/twilio/stateful-turn"

    session = get_call_session_by_twilio_sid(call_sid)

    if not session:
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

    if not session:
        return twiml_connect_realtime(
            caller_phone=caller,
            to_number=to_number,
            call_sid=call_sid,
            intro_message="I’m having trouble loading the call. I’ll connect you to the AI receptionist now.",
        )

    state_before = session.get("current_state") or "collect_reason"

    if not caller_text:
        response_text = session.get("last_message") or template_ask_reason()

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

        return twiml_gather(
            message=response_text,
            action_url=action_url,
            language="en-US",
        )

    existing_transcript = session.get("speech_result") or ""

    update_call(
        session.get("call_id"),
        {
            "speech_result": (
                (existing_transcript + "\n" if existing_transcript else "")
                + f"Caller: {caller_text}"
            ),
            "confidence": confidence,
        },
    )

    doctors = get_active_doctors_for_clinic(session.get("clinic_id"))

    parsed = await classify_caller_turn_with_openai(
        caller_text=caller_text,
        call_state=session,
        doctors=doctors,
    )

    transition = handle_state_transition(
        session=session,
        parsed=parsed,
        doctors=doctors,
    )

    updates = transition.get("updates") or {}
    response_text = transition.get("response_text") or template_ask_reason()
    state_after = transition.get("state_after") or updates.get("current_state") or state_before

    updated_session = update_call_session(
        session["id"],
        updates,
    )

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

    update_call(
        session.get("call_id"),
        {
            "summary": f"Stateful call state: {state_after}. Last action: {transition.get('action')}.",
        },
    )

    if transition.get("fallback_triggered"):
        return twiml_connect_realtime(
            caller_phone=caller,
            to_number=to_number,
            call_sid=call_sid,
            intro_message=response_text,
        )

    if state_after == "done":
        return twiml_say_and_hangup(response_text)

    return twiml_gather(
        message=response_text,
        action_url=action_url,
        language="en-US",
    )


# ---------------------------------------------------------------------
# Existing realtime fallback endpoint
# ---------------------------------------------------------------------

@app.websocket("/twilio/realtime")
async def twilio_realtime(websocket: WebSocket):
    await websocket.accept()
    print("Twilio realtime WebSocket connected")

    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY is missing")
        await websocket.close()
        return

    stream_sid = None
    current_call_id = None
    transcript_parts = []
    ai_transcript_buffer = ""

    current_clinic_id = None
    current_caller_phone = None
    current_doctors = []

    realtime_session_ready = False

    openai_url = f"wss://api.openai.com/v1/realtime?model={OPENAI_REALTIME_MODEL}"

    try:
        async with websockets.connect(
            openai_url,
            additional_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Safety-Identifier": "dental-ai-receptionist-test",
            },
        ) as openai_ws:
            print("Connected to OpenAI Realtime")

            BASE_REALTIME_INSTRUCTIONS = (
                "You are a concise, warm, and professional AI receptionist for Westview Dental in Vancouver, BC. "
                "Start the call naturally by greeting the caller and asking how you can help. "

                "Start in neutral English unless the caller clearly speaks another language first. "
                "Reply in the caller's clearly detected language. "
                "If the caller clearly speaks Persian/Farsi at any point, switch to Persian/Farsi and continue in Persian/Farsi. "
                "If the caller clearly asks to use another language, switch to that language. "
                "If the caller's speech is mixed, garbled, or unclear, do not switch languages based on that unclear fragment. "
                "When speech is unclear, stay in the last clearly established language and ask the caller to repeat clearly. "
                "Do not switch languages because of one random foreign-looking transcript fragment. "

                "Keep replies short, natural, and receptionist-like. "
                "Normally ask exactly one question at a time. "
                "Do not ask for more than one new field in the same reply. "
                "Do not ask for the patient's name. "
                "Use brief natural acknowledgements only when they help the call feel normal, such as: Sure, I can repeat that. "
                "Do not overuse filler or long status messages. "
                "If the caller asks to repeat, rephrase, say that again, or asks what you just said, repeat the last meaningful assistant message or the last offered options. "
                "Do not treat repeat, rephrase, say that again, what did you say, or can you repeat as a date, time, doctor, reason, yes, no, or slot choice. "
                "After repeating or rephrasing, ask the same pending question again. "

                "For appointment booking, do not force the caller to choose a doctor first. "
                "If the caller already mentions a doctor, remember that doctor preference. "
                "If the caller does not mention a doctor, ask the reason for the dental visit first. "
                "For reason, ask only why they want the dental visit. "

                "If the reason is specific enough to map to a dental service or symptom, accept it. "
                "If the caller only says a vague reason such as problem, issue, something is wrong, I need a dentist, or I have a concern, ask one follow-up question to clarify the dental problem before calling get_booking_options. "
                "Examples of specific enough reasons: tooth pain, cleaning, checkup, broken tooth, filling, crown, wisdom tooth, bleeding gums, swelling, emergency, or orthodontic concern. "
                "Do not call get_booking_options when the only reason is vague. "

                "Do not ask for confirmation of the reason unless it is unclear. "
                "If the reason is unclear, ask why they want the dental visit again. "

                "After the dental reason is clear, use the get_booking_options tool to find appointment options. "
                "The booking tool uses the treatment duration, eligible doctors, recurring doctor availability, and calendar events from the clinic database. "
                "If the caller already mentioned a doctor, include that doctor name in the tool call. "
                "If the caller did not mention a doctor, pass doctor_name as null. "

                "If the caller gives a preferred date, repeat only the understood date and ask if it is correct before using that date for slot search. "

                "Never introduce a date that was not clearly spoken by the caller or returned by the booking tool. "
                "Never ask whether a random date is correct. "
                "If the caller asks for repetition after slot options, repeat the same slot options exactly; do not ask for date confirmation. "
                "If no date is currently pending confirmation, do not ask 'Is [date] correct?'. "
                "Only confirm a date immediately after the caller clearly gave that date. "

                "The date is not collected until the caller clearly confirms it after you repeat it. "
                "If the caller says no, no matter the language, the date is rejected and not confirmed. "
                "If the caller says no and provides a corrected date, discard the old date, repeat only the corrected date, and ask if it is correct. "
                "If the caller says no without a clear correction, discard the old date and ask for the preferred date again. "
                "If no preferred date is given, search for the earliest available slots. "

                "Do not ask for a preferred time before using the booking tool. "
                "The preferred time should normally come from one of the suggested appointment slots. "

                "After the tool returns slot suggestions, offer exactly two suggestions when two are available. "
                "Each suggestion must include doctor name, date, and time. "
                "Ask which one works better. "

                "After slot suggestions are given, classify the caller's next answer as one of: "
                "select_suggested_slot, change_doctor, change_date, change_doctor_and_date, reject_without_alternative, ask_question, unclear. "

                "If the caller selects one of the suggested slots, accept the selection and say the request has been noted and the front desk will contact them to confirm. "

                "Only treat the caller as selecting a suggested slot if they clearly say the time, the first one, the second one, the earlier one, the later one, that one, or clearly repeat one of the offered options. "
                "Do not infer slot selection from unrelated words, names, greetings, foreign-language fragments, background speech, or unclear audio. "
                "If the answer after slot suggestions is unclear, ask: Did you prefer the first option or the second option? "
                "Do not say the request has been noted until the caller clearly chooses one suggested slot or clearly asks for front desk follow-up. "

                "Never say the appointment is confirmed. "

                "If the caller says a different doctor after suggestions, call get_booking_options again with the updated doctor and the same reason and date if available. "
                "If the caller says a different date after suggestions, confirm that date first, then call get_booking_options again with the updated date. "
                "If the caller says both a different doctor and a different date, update both, confirm the date, then call get_booking_options again. "

                "If the caller rejects the suggested slots without giving a new doctor or date, ask what date they prefer. "
                "If the caller still does not choose a slot, say the front desk will contact them to find another time. "

                "If the booking tool says the requested doctor does not provide the treatment, tell the caller that briefly and offer to check another eligible doctor. "
                "If the booking tool says no slots were found, tell the caller the front desk will contact them to find another time. "
                "If the booking tool says the service was not matched, ask the caller to briefly repeat the reason for the dental visit. "

                "If the caller's answer is garbled, mixed-language, unrelated, or low-confidence, do not convert it into a name, date, time, doctor, reason, or slot choice. "
                "Ask the same field again in the last clearly established language. "
                "Never turn unclear audio into a likely date such as next Tuesday, next Monday, April 22, April 15, or a likely time such as 3 PM or 9:30 AM. "
                "Random words, foreign-language fragments, unrelated words, or unclear sounds are not confirmation. "
                "Only clear yes/no answers in the caller's language count as confirmation. "

                "Do not say the request has been noted until the caller has selected one of the suggested appointment slots, or until the caller agrees that the front desk should follow up. "

                "For severe swelling, uncontrolled bleeding, facial trauma, or trouble breathing, advise emergency medical care immediately."
            )

            async def receive_from_twilio():
                nonlocal stream_sid
                nonlocal current_call_id
                nonlocal current_clinic_id
                nonlocal current_caller_phone
                nonlocal transcript_parts
                nonlocal current_doctors
                nonlocal realtime_session_ready

                try:
                    while True:
                        message = await websocket.receive_text()
                        data = json.loads(message)

                        event = data.get("event")

                        if event == "connected":
                            print("Twilio event: connected")

                        elif event == "start":
                            stream_sid = data["start"]["streamSid"]

                            start_data = data.get("start", {})
                            custom_params = start_data.get("customParameters", {})

                            call_sid = custom_params.get("call_sid") or start_data.get("callSid")
                            caller = normalize_phone(custom_params.get("caller_phone"))
                            to_number = normalize_phone(custom_params.get("to_number"))

                            print(f"Twilio event: start | streamSid={stream_sid}")
                            print(f"Realtime custom params | callSid={call_sid} from={caller} to={to_number}")

                            clinic = find_clinic_by_twilio_number(to_number)
                            clinic_id = clinic["id"] if clinic else None

                            current_clinic_id = clinic_id
                            current_caller_phone = caller

                            current_doctors = get_active_doctors_for_clinic(clinic_id)

                            print(f"Active doctors for clinic: {current_doctors}")

                            if len(current_doctors) > 1:
                                doctor_names = [
                                    doctor.get("display_name") or doctor.get("full_name")
                                    for doctor in current_doctors
                                    if doctor.get("display_name") or doctor.get("full_name")
                                ]

                                doctor_context = (
                                    " IMPORTANT CLINIC CONTEXT: "
                                    f"This clinic has multiple active doctors: {', '.join(doctor_names)}. "
                                    "Do not force the caller to choose a doctor first. "
                                    "If the caller mentions a doctor at any point, treat it as preferred_doctor_name and use that doctor for booking search. "
                                    "If the caller does not mention a doctor, ask the reason for the dental visit first. "
                                    "After the reason is clear, call the get_booking_options tool. "
                                    "If no doctor was requested, the tool will find eligible doctors for that treatment. "
                                    "If a doctor was requested, the tool will check that doctor and treatment combination. "
                                    "If the caller gives a preferred date, confirm the date before calling the tool with that date. "
                                    "After slot suggestions are given, if the caller says a different doctor or different date, call the tool again with the updated preference. "
                                    "If the caller selects one of the suggested slots, accept the selection and say the request has been noted and the front desk will contact them to confirm. "
                                    "If the caller rejects the suggested slots without a new doctor or date, ask what date they prefer. "
                                    "If the caller still does not choose a slot, say the front desk will contact them to find another time. "
                                    "Ask only one direct question at a time. "
                                    "Do not ask for the patient's name. "
                                )
                            else:
                                doctor_context = (
                                    " IMPORTANT CLINIC CONTEXT: "
                                    "This clinic has zero or one active doctor. "
                                    "Do not ask which doctor the caller prefers. "
                                    "Ask the reason for the dental visit first. "
                                    "After the reason is clear, call the get_booking_options tool to suggest appointment slots. "
                                    "If the caller gives a preferred date, confirm the date before calling the tool with that date. "
                                    "After slot suggestions are given, if the caller says a different date, call the tool again with the updated date. "
                                    "If the caller selects one of the suggested slots, accept the selection and say the request has been noted and the front desk will contact them to confirm. "
                                    "If the caller rejects the suggested slots without a new date, ask what date they prefer. "
                                    "If the caller still does not choose a slot, say the front desk will contact them to find another time. "
                                    "Ask only one direct question at a time. "
                                    "Do not ask for the patient's name. "
                                )

                            session_update = {
                                "type": "session.update",
                                "session": {
                                    "type": "realtime",
                                    "model": OPENAI_REALTIME_MODEL,
                                    "instructions": BASE_REALTIME_INSTRUCTIONS + doctor_context,
                                    "output_modalities": ["audio"],
                                    "audio": {
                                        "input": {
                                            "format": {
                                                "type": "audio/pcmu",
                                            },
                                            "transcription": {
                                                "model": "gpt-4o-transcribe",
                                            },
                                            "turn_detection": {
                                                "type": "server_vad",
                                                "threshold": 0.5,
                                                "prefix_padding_ms": 600,
                                                "silence_duration_ms": 700,
                                            },
                                        },
                                        "output": {
                                            "format": {
                                                "type": "audio/pcmu",
                                            },
                                            "voice": "alloy",
                                        },
                                    },
                                    "tracing": "auto",
                                    "tools": [
                                        {
                                            "type": "function",
                                            "name": "get_booking_options",
                                            "description": (
                                                "Find the best two appointment slot suggestions using doctor preference, "
                                                "dental reason or treatment, optional confirmed preferred date, doctor services, "
                                                "doctor recurring availability, and doctor calendar events."
                                            ),
                                            "parameters": {
                                                "type": "object",
                                                "properties": {
                                                    "doctor_name": {
                                                        "type": ["string", "null"],
                                                        "description": "Doctor name mentioned by the caller, or null if no doctor preference.",
                                                    },
                                                    "reason": {
                                                        "type": ["string", "null"],
                                                        "description": "Dental visit reason, symptom, or treatment requested by the caller.",
                                                    },
                                                    "preferred_date_raw": {
                                                        "type": ["string", "null"],
                                                        "description": "Preferred date if the caller gave one.",
                                                    },
                                                    "preferred_date_confirmed": {
                                                        "type": "boolean",
                                                        "description": "True only after the assistant repeated the date and the caller confirmed it.",
                                                    },
                                                },
                                                "required": [
                                                    "doctor_name",
                                                    "reason",
                                                    "preferred_date_raw",
                                                    "preferred_date_confirmed",
                                                ],
                                                "additionalProperties": False,
                                            },
                                        }
                                    ],
                                    "tool_choice": "auto",
                                },
                            }

                            await openai_ws.send(json.dumps(session_update))
                            print("Sent OpenAI session.update with clinic context and booking tool")
                            realtime_session_ready = True

                            saved_call = save_call_to_db(
                                clinic_id=clinic_id,
                                twilio_call_sid=call_sid,
                                caller_phone=caller,
                                speech_result="",
                                confidence=None,
                                intent="realtime",
                                urgency="normal",
                                summary="Realtime AI call started.",
                            )

                            if saved_call:
                                current_call_id = saved_call["id"]
                                print(f"Realtime call saved to DB: {current_call_id}")
                            else:
                                print("Realtime call was not saved to DB")

                        elif event == "media":
                            if not realtime_session_ready:
                                continue

                            payload = data["media"]["payload"]

                            await openai_ws.send(
                                json.dumps(
                                    {
                                        "type": "input_audio_buffer.append",
                                        "audio": payload,
                                    }
                                )
                            )

                        elif event == "stop":
                            print("Twilio event: stop")

                            if current_call_id and transcript_parts:
                                full_transcript = "\n".join(transcript_parts)

                                update_call(
                                    current_call_id,
                                    {
                                        "speech_result": full_transcript,
                                        "summary": "Realtime AI call completed.",
                                    },
                                )

                                caller_only_transcript = "\n".join(
                                    line for line in transcript_parts
                                    if line.startswith("Caller:")
                                )

                                appointment_details = await extract_appointment_details_with_openai(
                                    full_transcript,
                                    current_doctors,
                                )

                                preferred_doctor_name = appointment_details.get("preferred_doctor_name")

                                matched_doctor = match_doctor_from_name(
                                    current_doctors,
                                    preferred_doctor_name,
                                )

                                doctor_id = matched_doctor["id"] if matched_doctor else None

                                if matched_doctor:
                                    preferred_doctor_name = (
                                        matched_doctor.get("display_name")
                                        or matched_doctor.get("full_name")
                                        or preferred_doctor_name
                                    )

                                print(
                                    "Final appointment details extracted after call: "
                                    f"{appointment_details}"
                                )

                                service_match_input = caller_only_transcript

                                if appointment_details.get("reason"):
                                    service_match_input += "\n" + appointment_details.get("reason")

                                service_match = match_service_from_transcript(
                                    current_clinic_id,
                                    service_match_input,
                                )

                                patient_name = appointment_details.get("patient_name")

                                reason = (
                                    service_match["canonical_reason"]
                                    if service_match
                                    else appointment_details.get("reason")
                                )

                                preferred_date_raw = appointment_details.get("preferred_date_raw")
                                preferred_time_raw = appointment_details.get("preferred_time_raw")

                                date_confirmed = bool(appointment_details.get("date_confirmed"))
                                time_confirmed = bool(appointment_details.get("time_confirmed"))

                                if not date_confirmed:
                                    preferred_date_raw = None

                                if not time_confirmed:
                                    preferred_time_raw = None

                                preferred_time_combined = (
                                    ((preferred_date_raw or "") + " " + (preferred_time_raw or "")).strip()
                                    or None
                                )

                                urgency = (
                                    service_match["default_urgency"]
                                    if service_match
                                    else "normal"
                                )

                                save_call_extraction(
                                    clinic_id=current_clinic_id,
                                    call_id=current_call_id,
                                    raw_transcript=full_transcript,
                                    cleaned_transcript=appointment_details.get("notes"),
                                    detected_language=appointment_details.get("language"),
                                    patient_name=patient_name,
                                    service_category=(
                                        service_match["category_name"]
                                        if service_match
                                        else None
                                    ),
                                    canonical_reason=reason,
                                    preferred_time_raw=preferred_time_raw,
                                    preferred_datetime=None,
                                    urgency=urgency,
                                    confidence=appointment_details.get("confidence"),
                                    extraction_notes=json.dumps(
                                        appointment_details,
                                        ensure_ascii=False,
                                    ),
                                    preferred_date_raw=preferred_date_raw,
                                    preferred_date_confirmed=date_confirmed,
                                    preferred_time_confirmed=time_confirmed,
                                    doctor_id=doctor_id,
                                    preferred_doctor_name=preferred_doctor_name,
                                )

                                should_create_request = bool(
                                    patient_name
                                    or preferred_doctor_name
                                    or reason
                                    or preferred_date_raw
                                    or preferred_time_raw
                                )

                                if should_create_request:
                                    appointment_request = create_appointment_request(
                                        clinic_id=current_clinic_id,
                                        call_id=current_call_id,
                                        patient_phone=current_caller_phone,
                                        patient_name=patient_name,
                                        reason=reason,
                                        preferred_time=preferred_time_combined,
                                        urgency=urgency,
                                        status="new",
                                        doctor_id=doctor_id,
                                        preferred_doctor_name=preferred_doctor_name,
                                    )

                                    if appointment_request:
                                        updates = {
                                            "doctor_id": doctor_id,
                                            "preferred_doctor_name": preferred_doctor_name,
                                            "preferred_date_raw": preferred_date_raw,
                                            "preferred_time_raw": preferred_time_raw,
                                            "preferred_date_confirmed": date_confirmed,
                                            "preferred_time_confirmed": time_confirmed,
                                        }

                                        if service_match:
                                            updates.update(
                                                {
                                                    "service_category_id": service_match.get("category_id"),
                                                    "service_category_name": service_match.get("category_name"),
                                                    "duration_minutes": service_match.get("duration_minutes") or 30,
                                                }
                                            )

                                        update_appointment_request(
                                            appointment_request["id"],
                                            updates,
                                        )

                                    print(
                                        "Realtime appointment request created after-call AI extraction: "
                                        f"service={service_match}, details={appointment_details}"
                                    )

                                else:
                                    print(
                                        "No appointment request created after-call AI extraction. "
                                        f"service_match={service_match}, details={appointment_details}"
                                    )

                            else:
                                print(
                                    "Twilio stop received, but no current_call_id or transcript_parts found."
                                )

                            await openai_ws.close()
                            break

                except WebSocketDisconnect:
                    print("Twilio WebSocket disconnected")
                    await openai_ws.close()

                except Exception as e:
                    print(f"Twilio receive error: {e}")
                    await openai_ws.close()

            async def receive_from_openai():
                nonlocal stream_sid
                nonlocal transcript_parts
                nonlocal ai_transcript_buffer
                nonlocal current_clinic_id
                nonlocal current_doctors

                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)
                        event_type = response.get("type")

                        if event_type in ["session.created", "session.updated"]:
                            print(f"OpenAI event: {event_type}")

                        elif event_type == "response.created":
                            print("OpenAI event: response.created")

                        elif event_type in ["response.audio.delta", "response.output_audio.delta"]:
                            if stream_sid:
                                audio_delta = response.get("delta")

                                if audio_delta:
                                    await websocket.send_text(
                                        json.dumps(
                                            {
                                                "event": "media",
                                                "streamSid": stream_sid,
                                                "media": {
                                                    "payload": audio_delta,
                                                },
                                            }
                                        )
                                    )

                        elif event_type in [
                            "response.audio_transcript.delta",
                            "response.output_audio_transcript.delta",
                        ]:
                            transcript_delta = response.get("delta")
                            if transcript_delta:
                                ai_transcript_buffer += transcript_delta
                                print(f"AI transcript delta: {transcript_delta}")

                        elif event_type in [
                            "conversation.item.input_audio_transcription.completed",
                            "input_audio_buffer.transcription.completed",
                        ]:
                            user_transcript = response.get("transcript")
                            if user_transcript:
                                transcript_parts.append(f"Caller: {user_transcript}")
                                print(f"Caller transcript: {user_transcript}")

                        elif event_type in [
                            "response.audio_transcript.done",
                            "response.output_audio_transcript.done",
                        ]:
                            final_ai_transcript = response.get("transcript") or ai_transcript_buffer

                            if final_ai_transcript.strip():
                                transcript_parts.append(f"AI: {final_ai_transcript.strip()}")
                                print(f"AI transcript completed: {final_ai_transcript.strip()}")

                            ai_transcript_buffer = ""

                        elif event_type == "response.function_call_arguments.done":
                            tool_name = response.get("name")
                            tool_call_id = response.get("call_id")
                            arguments_raw = response.get("arguments") or "{}"

                            print(f"Realtime tool call requested: {tool_name} args={arguments_raw}")

                            if tool_name == "get_booking_options":
                                try:
                                    args = json.loads(arguments_raw)
                                except Exception as e:
                                    print(f"Failed to parse tool arguments: {e}")
                                    args = {}

                                tool_result = get_booking_options_for_ai(
                                    clinic_id=current_clinic_id,
                                    doctors=current_doctors,
                                    doctor_name=args.get("doctor_name"),
                                    reason=args.get("reason"),
                                    preferred_date_raw=args.get("preferred_date_raw"),
                                    preferred_date_confirmed=bool(
                                        args.get("preferred_date_confirmed")
                                    ),
                                )

                                print(f"Realtime tool result: {tool_result}")

                                await openai_ws.send(
                                    json.dumps(
                                        {
                                            "type": "conversation.item.create",
                                            "item": {
                                                "type": "function_call_output",
                                                "call_id": tool_call_id,
                                                "output": json.dumps(
                                                    tool_result,
                                                    ensure_ascii=False,
                                                ),
                                            },
                                        }
                                    )
                                )

                                await openai_ws.send(
                                    json.dumps(
                                        {
                                            "type": "response.create",
                                        }
                                    )
                                )

                        elif event_type == "response.done":
                            print("OpenAI event: response.done")

                        elif event_type == "error":
                            print(f"OpenAI error: {response}")

                        else:
                            print(f"OpenAI event: {event_type}")

                except Exception as e:
                    print(f"OpenAI receive error: {e}")

            await asyncio.gather(
                receive_from_twilio(),
                receive_from_openai(),
            )

    except Exception as e:
        print(f"Realtime bridge error: {e}")

    finally:
        print("Realtime bridge closed")


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
    reason: str = "my tooth hurts",
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


# ---------------------------------------------------------------------
# After-call realtime extraction
# ---------------------------------------------------------------------

async def extract_appointment_details_with_openai(
    transcript: str,
    doctors: list[dict] | None = None,
) -> dict:
    if not openai_client:
        return {
            "patient_name": None,
            "preferred_doctor_name": None,
            "doctor_confirmed": False,
            "reason": None,
            "preferred_date_raw": None,
            "preferred_time_raw": None,
            "name_confirmed": False,
            "date_confirmed": False,
            "time_confirmed": False,
            "reason_confirmed": False,
            "language": "unknown",
            "confidence": 0.0,
            "notes": "OpenAI client is not initialized.",
        }

    doctor_names = []

    for doctor in doctors or []:
        name = doctor.get("display_name") or doctor.get("full_name")
        if name:
            doctor_names.append(name)

    doctor_list_text = ", ".join(doctor_names) if doctor_names else "No doctor list provided."

    schema = {
        "type": "object",
        "properties": {
            "patient_name": {
                "type": ["string", "null"],
                "description": "Patient full name only if clearly provided or clearly confirmed.",
            },
            "preferred_doctor_name": {
                "type": ["string", "null"],
                "description": "The preferred doctor name if the caller clearly chose one, or 'no preference' if the caller clearly said they have no preference.",
            },
            "doctor_confirmed": {
                "type": "boolean",
                "description": "True if the caller clearly selected a doctor or clearly said they have no preference. Explicit yes/no confirmation is not required.",
            },
            "reason": {
                "type": ["string", "null"],
                "description": "Dental visit reason only if clearly provided or understandable.",
            },
            "preferred_date_raw": {
                "type": ["string", "null"],
                "description": "Preferred appointment date only if clearly provided or confirmed.",
            },
            "preferred_time_raw": {
                "type": ["string", "null"],
                "description": "Preferred appointment time or selected suggested slot time only if clearly provided or selected.",
            },
            "name_confirmed": {
                "type": "boolean",
                "description": "True only if the assistant repeated the name and the caller clearly confirmed it.",
            },
            "date_confirmed": {
                "type": "boolean",
                "description": "True only if the assistant repeated the date and the caller clearly confirmed it, or the caller selected a suggested slot with a specific date.",
            },
            "time_confirmed": {
                "type": "boolean",
                "description": "True only if the assistant repeated the time and the caller clearly confirmed it, or the caller selected a suggested slot with a specific time.",
            },
            "reason_confirmed": {
                "type": "boolean",
                "description": "True if the reason was clearly stated. Explicit yes/no confirmation is not required for reason.",
            },
            "language": {
                "type": ["string", "null"],
                "description": "Main caller language, such as fa, en, es, or unknown.",
            },
            "confidence": {
                "type": "number",
                "description": "Extraction confidence from 0 to 1.",
            },
            "notes": {
                "type": ["string", "null"],
                "description": "Short explanation of missing, rejected, unclear, selected, or uncertain values.",
            },
        },
        "required": [
            "patient_name",
            "preferred_doctor_name",
            "doctor_confirmed",
            "reason",
            "preferred_date_raw",
            "preferred_time_raw",
            "name_confirmed",
            "date_confirmed",
            "time_confirmed",
            "reason_confirmed",
            "language",
            "confidence",
            "notes",
        ],
        "additionalProperties": False,
    }

    response = await openai_client.responses.create(
        model=OPENAI_EXTRACTION_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    "Extract structured appointment details from this phone call transcript. "
                    "Use only information supported by the transcript. "
                    "Do not guess or invent patient names, doctor names, dates, times, or reasons. "

                    f"The available doctors for this clinic are: {doctor_list_text}. "
                    "If the caller says a doctor name approximately, phonetically, partially, or in another language, "
                    "match it to the closest available doctor from the provided doctor list. "
                    "For example, Robert, Roberts, Rabert, or دکتر رابرت should match Dr. Roberts if Dr. Roberts is in the list. "
                    "If the caller first gives an unclear doctor answer, but later clearly mentions a doctor, use the later clear doctor. "
                    "If the caller clearly says no preference, set preferred_doctor_name to 'no preference'. "
                    "If the caller did not clearly choose a doctor and did not say no preference, set preferred_doctor_name to null. "

                    "For date and time confirmation, mark date_confirmed or time_confirmed true if the assistant repeated that value "
                    "and the caller clearly agreed directly after that confirmation question. "
                    "Also mark them true if the assistant offered specific appointment slots and the caller clearly selected one of those slots. "
                    "Answers like yes, yeah, correct, درست, بله, آره, ja, oui count as confirmation. "
                    "Answers like no, nope, نه, いや count as rejection. "

                    "If the caller rejected a repeated date or time, do not save the rejected value. "
                    "If the caller corrected a value and then confirmed it, save the corrected value. "
                    "If the caller selected the first or second offered slot, extract that slot's date and time from the assistant's offered options. "
                    "If a value is unclear, garbled, mixed-language, or uncertain, set it to null and explain in notes. "

                    "For reason, explicit yes/no confirmation is not required if the caller's reason was understandable."
                ),
            },
            {
                "role": "user",
                "content": transcript,
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "appointment_extraction",
                "schema": schema,
                "strict": True,
            }
        },
    )

    try:
        return json.loads(response.output_text)
    except Exception as e:
        return {
            "patient_name": None,
            "preferred_doctor_name": None,
            "doctor_confirmed": False,
            "reason": None,
            "preferred_date_raw": None,
            "preferred_time_raw": None,
            "name_confirmed": False,
            "date_confirmed": False,
            "time_confirmed": False,
            "reason_confirmed": False,
            "language": "unknown",
            "confidence": 0.0,
            "notes": f"Failed to parse extraction JSON: {e}",
        }