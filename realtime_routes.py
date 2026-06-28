import json
import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from openai import AsyncOpenAI
import websockets

import os
from twilio.rest import Client as TwilioClient

from config import (
    OPENAI_API_KEY,
    OPENAI_REALTIME_MODEL,
    OPENAI_EXTRACTION_MODEL,
)

from prompts import (
    build_extraction_system_prompt,
    build_short_audio_response_instructions,
    build_full_realtime_instructions,
    build_initial_greeting_instructions,
)

from openai_usage_tracker import (
    create_openai_usage_totals,
    track_realtime_response_done,
    persist_call_openai_usage,
    print_usage_summary,
)

from supabase_service import (
    normalize_phone,
    find_clinic_by_twilio_number,
    find_patients_by_phone,
    build_patient_options_for_ai,
    get_patient_display_name,
    save_call_to_db,
    update_call,
    match_service_from_transcript,
    save_call_extraction,
    get_active_doctors_for_clinic,
    match_doctor_from_name,
    get_booking_options_for_ai,
    create_appointment_request,
    update_appointment_request,
    get_upcoming_appointments_for_ai,
    cancel_appointment_for_ai,
    reschedule_appointment_for_ai,
    get_faq_answer_for_ai,
    get_working_hours_for_ai,
)

router = APIRouter()

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")

twilio_client = (
    TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN
    else None
)


async def end_twilio_call(call_sid: str | None):
    if not call_sid:
        print("Cannot end call: missing call_sid")
        return

    if not twilio_client:
        print("Cannot end call: Twilio client is not initialized")
        return

    try:
        await asyncio.to_thread(
            lambda: twilio_client.calls(call_sid).update(status="completed")
        )

        print(f"Twilio call ended: {call_sid}")

    except Exception as e:
        print(f"Failed to end Twilio call {call_sid}: {e}")

def sanitize_booking_options_for_patient(tool_result: dict) -> dict:
    """
    Keep internal IDs needed for booking/rescheduling,
    but remove doctor names from the model-visible tool output
    so the assistant does not say doctor names by default.
    """
    if not isinstance(tool_result, dict):
        return tool_result

    sanitized = dict(tool_result)

    slots = sanitized.get("slots")

    if isinstance(slots, list):
        sanitized_slots = []

        for slot in slots:
            if not isinstance(slot, dict):
                sanitized_slots.append(slot)
                continue

            clean_slot = dict(slot)

            # Do not expose doctor/provider names to the model voice response.
            clean_slot.pop("doctor_name", None)
            clean_slot.pop("doctor_display_name", None)
            clean_slot.pop("doctor_full_name", None)
            clean_slot.pop("provider_name", None)
            clean_slot.pop("clinician_name", None)

            # If there is a nested doctor/provider object, keep only the id.
            doctor = clean_slot.get("doctor")
            if isinstance(doctor, dict):
                clean_slot["doctor"] = {
                    "id": doctor.get("id") or doctor.get("doctor_id")
                }

            provider = clean_slot.get("provider")
            if isinstance(provider, dict):
                clean_slot["provider"] = {
                    "id": provider.get("id") or provider.get("doctor_id")
                }

            sanitized_slots.append(clean_slot)

        sanitized["slots"] = sanitized_slots[:1]

    sanitized["patient_facing_instruction"] = (
        "Offer only the date and time to the caller. "
        "Do not mention doctor names unless the caller specifically asks."
    )

    return sanitized


async def extract_appointment_details_with_openai(
    transcript: str,
    doctors: list[dict] | None = None,
    patient_candidates: list[dict] | None = None,
    booking_options_history: list[dict] | None = None,
) -> dict:
    if not openai_client:
        return {
            "patient_id": None,
            "patient_identity_confirmed": False,
            "patient_name": None,
            "preferred_doctor_name": None,
            "doctor_confirmed": False,
            "selected_slot_doctor_id": None,
            "selected_slot_doctor_name": None,
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

    doctor_list_text = (
        ", ".join(doctor_names) if doctor_names else "No doctor list provided."
    )

    patient_options = build_patient_options_for_ai(patient_candidates or [])

    patient_list_text = (
        json.dumps(patient_options, ensure_ascii=False)
        if patient_options
        else "No existing patients were found for the caller phone number."
    )

    booking_options_text = (
        json.dumps(booking_options_history or [], ensure_ascii=False)
        if booking_options_history
        else "No booking options were offered."
    )

    schema = {
        "type": "object",
        "properties": {
            "patient_id": {
                "type": ["string", "null"],
                "description": (
                    "Existing patient UUID only if the caller clearly confirmed "
                    "or selected one of the provided existing patient candidates. "
                    "Never invent an id."
                ),
            },
            "patient_identity_confirmed": {
                "type": "boolean",
                "description": (
                    "True only if the caller clearly confirmed the suggested patient "
                    "or clearly selected one of the listed existing patients."
                ),
            },
            "patient_name": {
                "type": ["string", "null"],
                "description": (
                    "Patient full name only if clearly provided, clearly confirmed, "
                    "or available from a confirmed existing patient candidate."
                ),
            },
            "preferred_doctor_name": {
                "type": ["string", "null"],
                "description": (
                    "The preferred doctor name if the caller clearly chose one, "
                    "or 'no preference' if the caller clearly said they have no preference."
                ),
            },
            "doctor_confirmed": {
                "type": "boolean",
                "description": (
                    "True if the caller clearly selected a doctor or clearly said they have no preference. "
                    "Explicit yes/no confirmation is not required."
                ),
            },
            "selected_slot_doctor_id": {
                "type": ["string", "null"],
                "description": (
                    "Doctor id from the selected offered appointment slot. "
                    "Use only doctor_id values from the provided booking_options_history. "
                    "Set null if no offered slot was clearly selected."
                ),
            },
            "selected_slot_doctor_name": {
                "type": ["string", "null"],
                "description": (
                    "Doctor name from the selected offered appointment slot. "
                    "Use only doctor_name values from the provided booking_options_history. "
                    "Set null if no offered slot was clearly selected."
                ),
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
                "description": (
                    "Preferred appointment time or selected suggested slot time only if clearly provided or selected."
                ),
            },
            "name_confirmed": {
                "type": "boolean",
                "description": (
                    "True if the patient name was clearly confirmed, or if an existing patient candidate was confirmed."
                ),
            },
            "date_confirmed": {
                "type": "boolean",
                "description": (
                    "True only if the assistant repeated the date and the caller clearly confirmed it, "
                    "or the caller selected a suggested slot with a specific date."
                ),
            },
            "time_confirmed": {
                "type": "boolean",
                "description": (
                    "True only if the assistant repeated the time and the caller clearly confirmed it, "
                    "or the caller selected a suggested slot with a specific time."
                ),
            },
            "reason_confirmed": {
                "type": "boolean",
                "description": (
                    "True if the reason was clearly stated. Explicit yes/no confirmation is not required for reason."
                ),
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
                "description": (
                    "Short explanation of missing, rejected, unclear, selected, or uncertain values."
                ),
            },
        },
        "required": [
            "patient_id",
            "patient_identity_confirmed",
            "patient_name",
            "preferred_doctor_name",
            "doctor_confirmed",
            "selected_slot_doctor_id",
            "selected_slot_doctor_name",
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

    try:
        extraction_started_at = time.perf_counter()

        response = await openai_client.responses.create(
            model=OPENAI_EXTRACTION_MODEL,
            input=[
                {
                    "role": "system",
                    "content": build_extraction_system_prompt(
                        doctor_list_text=doctor_list_text,
                        patient_list_text=patient_list_text,
                        booking_options_text=booking_options_text,
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

        extraction_duration = time.perf_counter() - extraction_started_at
        print(
            "Appointment extraction completed | "
            f"duration_seconds={extraction_duration:.3f}"
        )

        return json.loads(response.output_text)

    except Exception as e:
        print(f"Appointment extraction failed: {e}")

        return {
            "patient_id": None,
            "patient_identity_confirmed": False,
            "patient_name": None,
            "preferred_doctor_name": None,
            "doctor_confirmed": False,
            "selected_slot_doctor_id": None,
            "selected_slot_doctor_name": None,
            "reason": None,
            "preferred_date_raw": None,
            "preferred_time_raw": None,
            "name_confirmed": False,
            "date_confirmed": False,
            "time_confirmed": False,
            "reason_confirmed": False,
            "language": "unknown",
            "confidence": 0.0,
            "notes": f"Failed to extract appointment details: {e}",
        }


@router.websocket("/twilio/realtime")
async def twilio_realtime(websocket: WebSocket):
    await websocket.accept()
    print("Twilio realtime WebSocket connected")

    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY is missing")
        await websocket.close()
        return

    stream_sid = None
    current_call_id = None
    current_twilio_call_sid = None
    current_response_id = None
    transcript_parts = []
    ai_transcript_buffer = ""

    end_call_requested = False
    end_call_task = None

    openai_usage_totals = create_openai_usage_totals()

    current_clinic_id = None
    current_clinic_name = "the dental clinic"
    current_caller_phone = None
    current_doctors = []
    current_patient_candidates = []
    booking_options_history = []

    appointment_request_write_needed = False
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

            short_audio_response_instructions = build_short_audio_response_instructions()

            async def create_short_audio_response():
                await openai_ws.send(
                    json.dumps(
                        {
                            "type": "response.create",
                            "response": {
                                "instructions": short_audio_response_instructions,
                            },
                        }
                    )
                )

            async def schedule_call_end(reason: str):
                nonlocal end_call_task

                if end_call_task:
                    print(f"Call end already scheduled | reason={reason}")
                    return

                print(
                    "Call end scheduled | "
                    f"reason={reason}, "
                    f"current_twilio_call_sid={current_twilio_call_sid}"
                )

                async def delayed_end():
                    await asyncio.sleep(0.7)
                    await end_twilio_call(current_twilio_call_sid)

                end_call_task = asyncio.create_task(delayed_end())
                
            async def receive_from_twilio():
                nonlocal stream_sid
                nonlocal current_call_id
                nonlocal current_clinic_id
                nonlocal current_twilio_call_sid
                nonlocal current_clinic_name
                nonlocal current_caller_phone
                nonlocal transcript_parts
                nonlocal current_doctors
                nonlocal current_patient_candidates
                nonlocal booking_options_history
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

                            call_sid = custom_params.get("call_sid") or start_data.get(
                                "callSid"
                            )
                            current_twilio_call_sid = call_sid
                            caller = normalize_phone(custom_params.get("caller_phone"))
                            to_number = normalize_phone(custom_params.get("to_number"))

                            print(f"Twilio event: start | streamSid={stream_sid}")
                            print(
                                f"Realtime custom params | callSid={call_sid} "
                                f"from={caller} to={to_number}"
                            )

                            clinic = find_clinic_by_twilio_number(to_number)
                            clinic_id = clinic["id"] if clinic else None
                            clinic_name = clinic.get("name") if clinic else None

                            current_clinic_id = clinic_id
                            current_clinic_name = clinic_name or "the dental clinic"
                            current_caller_phone = caller

                            print(
                                f"Resolved clinic | id={current_clinic_id} "
                                f"name={current_clinic_name}"
                            )

                            current_doctors = get_active_doctors_for_clinic(clinic_id)
                            print(f"Active doctors for clinic: {current_doctors}")

                            current_patient_candidates = find_patients_by_phone(
                                clinic_id=clinic_id,
                                phone=caller,
                            )

                            booking_options_history = []

                            print(
                                "Patient candidates for caller phone: "
                                f"{current_patient_candidates}"
                            )

                            full_realtime_instructions = build_full_realtime_instructions(
                                current_clinic_name=current_clinic_name,
                                current_doctors=current_doctors,
                                current_patient_candidates=current_patient_candidates,
                                get_patient_display_name=get_patient_display_name,
                                build_patient_options_for_ai=build_patient_options_for_ai,
                            )

                            session_update = {
                                "type": "session.update",
                                "session": {
                                    "type": "realtime",
                                    "model": OPENAI_REALTIME_MODEL,
                                    "instructions": full_realtime_instructions,
                                    "output_modalities": ["audio"],
                                    "audio": {
                                        "input": {
                                            "format": {"type": "audio/pcmu"},
                                            "transcription": {
                                                "model": "gpt-4o-transcribe"
                                            },
                                            "turn_detection": {
                                                "type": "server_vad",
                                                "threshold": 0.5,
                                                "prefix_padding_ms": 600,
                                                "silence_duration_ms": 700,
                                                "create_response": True,
                                                "interrupt_response": True,
                                            },
                                        },
                                        "output": {
                                            "format": {"type": "audio/pcmu"},
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
                                                    "preferred_time_raw": {
                                                        "type": ["string", "null"],
                                                        "description": (
                                                            "Preferred time or time range if the caller gave one, such as morning, afternoon, "
                                                            "evening, after 2 PM, before noon, 3 PM, between 2 and 4, from 3 to 5, "
                                                            "or equivalent time-preference phrases in the caller's language. "
                                                            "Use null if no time preference."
                                                        ),
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
                                                    "preferred_time_raw",
                                                    "preferred_date_confirmed",
                                                ],
                                                "additionalProperties": False,
                                            },
                                        },
                                        {
                                            "type": "function",
                                            "name": "note_booking_request",
                                            "description": (
                                                "Use this only after the caller clearly accepts the single offered appointment slot. "
                                                "This marks the new booking request as completed for after-call saving. "
                                                "Do not use this for unclear speech, random words, rejection, cancellation, lookup, FAQ, or reschedule."
                                            ),
                                            "parameters": {
                                                "type": "object",
                                                "properties": {},
                                                "required": [],
                                                "additionalProperties": False,
                                            },
                                        },
                                        {
                                            "type": "function",
                                            "name": "get_faq_answer",
                                            "description": (
                                                "Use this when the caller asks a general clinic FAQ question, "
                                                "such as insurance, direct billing, parking, children, emergency availability, "
                                                "wisdom teeth, clinic services, cancellation policy, payment policy, or other "
                                                "non-booking clinic questions. This tool returns the clinic-specific answer."
                                            ),
                                            "parameters": {
                                                "type": "object",
                                                "properties": {
                                                    "caller_question": {
                                                        "type": "string",
                                                        "description": "The caller's exact clinic question or statement.",
                                                    },
                                                },
                                                "required": ["caller_question"],
                                                "additionalProperties": False,
                                            },
                                        },
                                        {
                                            "type": "function",
                                            "name": "get_working_hours",
                                            "description": (
                                                "Use this when the caller asks about clinic hours, opening hours, closing time, "
                                                "whether the clinic is open on a specific date or day, or a specific doctor's working hours."
                                            ),
                                            "parameters": {
                                                "type": "object",
                                                "properties": {
                                                    "caller_question": {
                                                        "type": "string",
                                                        "description": "The caller's exact question about hours or working availability.",
                                                    },
                                                    "doctor_name": {
                                                        "type": ["string", "null"],
                                                        "description": "Doctor name if the caller asks about a specific doctor, otherwise null.",
                                                    },
                                                    "date_raw": {
                                                        "type": ["string", "null"],
                                                        "description": "Specific day or date mentioned by the caller, such as today, tomorrow, Monday, July 20, or null for general weekly hours.",
                                                    },
                                                },
                                                "required": [
                                                    "caller_question",
                                                    "doctor_name",
                                                    "date_raw",
                                                ],
                                                "additionalProperties": False,
                                            },
                                        },
                                        {
                                            "type": "function",
                                            "name": "get_upcoming_appointments",
                                            "description": (
                                                "Look up upcoming appointments for a confirmed existing patient. "
                                                "Use this when the caller asks about appointment time, appointment reminder, "
                                                "or when the caller wants to cancel or reschedule an existing appointment."
                                            ),
                                            "parameters": {
                                                "type": "object",
                                                "properties": {
                                                    "patient_id": {
                                                        "type": "string",
                                                        "description": "Confirmed existing patient id.",
                                                    },
                                                },
                                                "required": ["patient_id"],
                                                "additionalProperties": False,
                                            },
                                        },
                                        {
                                            "type": "function",
                                            "name": "cancel_appointment",
                                            "description": (
                                                "Cancel one confirmed upcoming appointment after patient identity is confirmed, "
                                                "the appointment is identified, and the caller gives final clear yes confirmation."
                                            ),
                                            "parameters": {
                                                "type": "object",
                                                "properties": {
                                                    "patient_id": {
                                                        "type": "string",
                                                        "description": "Confirmed existing patient id.",
                                                    },
                                                    "appointment_id": {
                                                        "type": "string",
                                                        "description": "The exact appointment id selected from get_upcoming_appointments.",
                                                    },
                                                },
                                                "required": [
                                                    "patient_id",
                                                    "appointment_id",
                                                ],
                                                "additionalProperties": False,
                                            },
                                        },
                                        {
                                            "type": "function",
                                            "name": "reschedule_appointment",
                                            "description": (
                                                "Reschedule one confirmed upcoming appointment after patient identity is confirmed, "
                                                "the original appointment is identified, and the caller clearly selects a new offered slot."
                                            ),
                                            "parameters": {
                                                "type": "object",
                                                "properties": {
                                                    "patient_id": {
                                                        "type": "string",
                                                        "description": "Confirmed existing patient id.",
                                                    },
                                                    "appointment_id": {
                                                        "type": "string",
                                                        "description": "The exact original appointment id selected from get_upcoming_appointments.",
                                                    },
                                                    "doctor_id": {
                                                        "type": "string",
                                                        "description": "Doctor id from the selected new slot returned by get_booking_options.",
                                                    },
                                                    "start_time_iso": {
                                                        "type": "string",
                                                        "description": "starts_at value from the selected new slot returned by get_booking_options.",
                                                    },
                                                    "end_time_iso": {
                                                        "type": "string",
                                                        "description": "ends_at value from the selected new slot returned by get_booking_options.",
                                                    },
                                                },
                                                "required": [
                                                    "patient_id",
                                                    "appointment_id",
                                                    "doctor_id",
                                                    "start_time_iso",
                                                    "end_time_iso",
                                                ],
                                                "additionalProperties": False,
                                            },
                                        },
                                    ],
                                    "tool_choice": "auto",
                                },
                            }

                            await openai_ws.send(json.dumps(session_update))
                            print(
                                "Sent OpenAI session.update with clinic, patient context and tools"
                            )
                            realtime_session_ready = True

                            initial_response_instructions = (
                                build_initial_greeting_instructions(
                                    current_clinic_name=current_clinic_name,
                                )
                            )

                            await openai_ws.send(
                                json.dumps(
                                    {
                                        "type": "response.create",
                                        "response": {
                                            "instructions": initial_response_instructions,
                                        },
                                    }
                                )
                            )

                            print("Sent initial OpenAI greeting response.create")

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

                                persist_call_openai_usage(
                                    call_id=current_call_id,
                                    totals=openai_usage_totals,
                                    update_call_func=update_call,
                                    model=OPENAI_REALTIME_MODEL,
                                    extra_updates={
                                        "speech_result": full_transcript,
                                        "summary": "Realtime AI call completed.",
                                    },
                                )

                                caller_only_transcript = "\n".join(
                                    line
                                    for line in transcript_parts
                                    if line.startswith("Caller:")
                                )

                                appointment_details = (
                                    await extract_appointment_details_with_openai(
                                        full_transcript,
                                        current_doctors,
                                        current_patient_candidates,
                                        booking_options_history,
                                    )
                                )

                                preferred_doctor_name = appointment_details.get(
                                    "preferred_doctor_name"
                                )

                                selected_slot_doctor_id = appointment_details.get(
                                    "selected_slot_doctor_id"
                                )
                                selected_slot_doctor_name = appointment_details.get(
                                    "selected_slot_doctor_name"
                                )

                                doctor_id = selected_slot_doctor_id or None

                                if selected_slot_doctor_name:
                                    preferred_doctor_name = selected_slot_doctor_name

                                if not doctor_id:
                                    matched_doctor = match_doctor_from_name(
                                        current_doctors,
                                        preferred_doctor_name,
                                    )

                                    doctor_id = (
                                        matched_doctor["id"]
                                        if matched_doctor
                                        else None
                                    )

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

                                extracted_reason = appointment_details.get("reason")

                                service_match = None

                                if extracted_reason:
                                    service_match = match_service_from_transcript(
                                        current_clinic_id,
                                        extracted_reason,
                                    )

                                if not service_match:
                                    service_match = match_service_from_transcript(
                                        current_clinic_id,
                                        caller_only_transcript,
                                    )

                                patient_name = appointment_details.get("patient_name")
                                patient_id = appointment_details.get("patient_id")
                                patient_identity_confirmed = bool(
                                    appointment_details.get(
                                        "patient_identity_confirmed"
                                    )
                                )

                                valid_patient_ids = {
                                    patient.get("id")
                                    for patient in current_patient_candidates
                                    if patient.get("id")
                                }

                                if (
                                    not patient_identity_confirmed
                                    or patient_id not in valid_patient_ids
                                ):
                                    patient_id = None

                                if patient_id:
                                    matched_patient = next(
                                        (
                                            patient
                                            for patient in current_patient_candidates
                                            if patient.get("id") == patient_id
                                        ),
                                        None,
                                    )

                                    if matched_patient:
                                        patient_name = (
                                            matched_patient.get("full_name")
                                            or patient_name
                                        )

                                reason = (
                                    service_match["canonical_reason"]
                                    if service_match
                                    else extracted_reason
                                )

                                preferred_date_raw = appointment_details.get(
                                    "preferred_date_raw"
                                )
                                preferred_time_raw = appointment_details.get(
                                    "preferred_time_raw"
                                )

                                date_confirmed = bool(
                                    appointment_details.get("date_confirmed")
                                )
                                time_confirmed = bool(
                                    appointment_details.get("time_confirmed")
                                )

                                accepted_slot = None

                                if booking_options_history:
                                    accepted_slot = booking_options_history[-1].get("accepted_slot")

                                if appointment_request_write_needed and accepted_slot:
                                    preferred_date_raw = accepted_slot.get("date")
                                    preferred_time_raw = accepted_slot.get("start_time")

                                    date_confirmed = True
                                    time_confirmed = True

                                    doctor_id = accepted_slot.get("doctor_id") or doctor_id
                                    preferred_doctor_name = (
                                        accepted_slot.get("doctor_name")
                                        or accepted_slot.get("doctor_display_name")
                                        or preferred_doctor_name
                                    )

                                else:
                                    if not date_confirmed:
                                        preferred_date_raw = None

                                    if not time_confirmed:
                                        preferred_time_raw = None

                                preferred_time_combined = (
                                    (
                                        (preferred_date_raw or "")
                                        + " "
                                        + (preferred_time_raw or "")
                                    ).strip()
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
                                    detected_language=appointment_details.get(
                                        "language"
                                    ),
                                    patient_id=patient_id,
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

                                non_booking_management_phrases = [
                                    "when is my appointment",
                                    "what time is my appointment",
                                    "remind me of my appointment",
                                    "appointment time",
                                    "upcoming appointment",
                                    "cancel my appointment",
                                    "cancel appointment",
                                    "cancel the appointment",
                                    "reschedule my appointment",
                                    "reschedule appointment",
                                    "change my appointment",
                                    "move my appointment",
                                    "modify my appointment",
                                    "وقت من کیه",
                                    "ساعت وقتم",
                                    "وقت دندان",
                                    "زمان وقتم",
                                    "وقتمو کنسل",
                                    "وقتم رو کنسل",
                                    "کنسل کنم",
                                    "کنسل کردن وقت",
                                    "وقتمو عوض",
                                    "وقتم رو عوض",
                                    "تغییر وقت",
                                    "عوض کردن وقت",
                                    "جابجا کردن وقت",
                                ]

                                transcript_lower = caller_only_transcript.lower()

                                raw_non_booking_management_call = any(
                                    phrase.lower() in transcript_lower
                                    for phrase in non_booking_management_phrases
                                )

                                slot_was_selected = bool(
                                    preferred_date_raw
                                    and preferred_time_raw
                                    and date_confirmed
                                    and time_confirmed
                                )

                                request_status = (
                                    "new" if slot_was_selected else "needs_followup"
                                )

                                accepted_slot = None

                                if booking_options_history:
                                    accepted_slot = booking_options_history[-1].get("accepted_slot")

                                booking_flow_completed = bool(
                                    appointment_request_write_needed
                                    and accepted_slot
                                )

                                is_non_booking_management_call = bool(
                                    raw_non_booking_management_call
                                    and not booking_flow_completed
                                )

                                should_create_request = bool(
                                    booking_flow_completed
                                    and not is_non_booking_management_call
                                )

                                print(
                                    "Appointment request decision | "
                                    f"appointment_request_write_needed={appointment_request_write_needed}, "
                                    f"is_non_booking_management_call={is_non_booking_management_call}, "
                                    f"slot_was_selected={slot_was_selected}, "
                                    f"request_status={request_status}, "
                                    f"reason={reason}, "
                                    f"extracted_reason={extracted_reason}, "
                                    f"preferred_date_raw={preferred_date_raw}, "
                                    f"preferred_time_raw={preferred_time_raw}, "
                                    f"date_confirmed={date_confirmed}, "
                                    f"time_confirmed={time_confirmed}, "
                                    f"doctor_id={doctor_id}, "
                                    f"preferred_doctor_name={preferred_doctor_name}, "
                                    f"booking_options_history_count={len(booking_options_history)}, "
                                    f"should_create_request={should_create_request}"
                                )

                                if should_create_request:
                                    appointment_request = create_appointment_request(
                                        clinic_id=current_clinic_id,
                                        call_id=current_call_id,
                                        patient_phone=current_caller_phone,
                                        patient_id=patient_id,
                                        patient_name=patient_name,
                                        reason=(
                                            reason
                                            or extracted_reason
                                            or "Appointment request needs follow-up"
                                        ),
                                        preferred_time=preferred_time_combined,
                                        urgency=urgency,
                                        status=request_status,
                                        doctor_id=doctor_id,
                                        preferred_doctor_name=preferred_doctor_name,
                                    )

                                    if appointment_request:
                                        updates = {
                                            "patient_id": patient_id,
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
                                                    "service_category_id": service_match.get(
                                                        "category_id"
                                                    ),
                                                    "service_category_name": service_match.get(
                                                        "category_name"
                                                    ),
                                                    "duration_minutes": service_match.get(
                                                        "duration_minutes"
                                                    )
                                                    or 30,
                                                }
                                            )

                                        update_appointment_request(
                                            appointment_request["id"],
                                            updates,
                                        )

                                    print(
                                        "Realtime appointment request created after-call AI extraction: "
                                        f"status={request_status}, patient_id={patient_id}, "
                                        f"service={service_match}, details={appointment_details}"
                                    )

                                else:
                                    print(
                                        "No appointment request created after-call AI extraction. "
                                        f"appointment_request_write_needed={appointment_request_write_needed}, "
                                        f"is_non_booking_management_call={is_non_booking_management_call}, "
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
                nonlocal current_response_id
                nonlocal transcript_parts
                nonlocal ai_transcript_buffer
                nonlocal end_call_requested
                nonlocal current_clinic_id
                nonlocal current_doctors
                nonlocal booking_options_history
                nonlocal openai_usage_totals
                nonlocal current_call_id
                nonlocal appointment_request_write_needed
                nonlocal current_caller_phone

                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)
                        event_type = response.get("type")

                        if event_type in ["session.created", "session.updated"]:
                            print(f"OpenAI event: {event_type}")

                        elif event_type == "input_audio_buffer.speech_started":
                            print("OpenAI event: input_audio_buffer.speech_started")

                            if end_call_requested:
                                print(
                                    "Ignoring caller speech because call end is already requested | "
                                    f"current_twilio_call_sid={current_twilio_call_sid}"
                                )
                                continue

                            if current_response_id:
                                try:
                                    await openai_ws.send(
                                        json.dumps(
                                            {
                                                "type": "response.cancel",
                                            }
                                        )
                                    )
                                    print(f"Cancelled active OpenAI response: {current_response_id}")
                                except Exception as e:
                                    print(f"Failed to cancel active response: {e}")

                                current_response_id = None

                            if stream_sid:
                                await websocket.send_text(
                                    json.dumps(
                                        {
                                            "event": "clear",
                                            "streamSid": stream_sid,
                                        }
                                    )
                                )
                                print("Sent Twilio clear event")
                   
                        elif event_type == "input_audio_buffer.speech_stopped":
                            print("OpenAI event: input_audio_buffer.speech_stopped")

                        elif event_type == "response.created":
                            current_response_id = response.get("response", {}).get("id")
                            print(f"OpenAI event: response.created | response_id={current_response_id}")

                        elif event_type in [
                            "response.audio.delta",
                            "response.output_audio.delta",
                        ]:
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
                            final_ai_transcript = (
                                response.get("transcript") or ai_transcript_buffer
                            )

                            if final_ai_transcript.strip():
                                transcript_parts.append(
                                    f"AI: {final_ai_transcript.strip()}"
                                )
                                print(
                                    "AI transcript completed: "
                                    f"{final_ai_transcript.strip()}"
                                )

                            ai_transcript_buffer = ""
                        elif event_type == "response.function_call_arguments.done":
                            tool_name = response.get("name")
                            tool_call_id = response.get("call_id")
                            arguments_raw = response.get("arguments") or "{}"

                            print(
                                f"Realtime tool call requested: {tool_name} "
                                f"args={arguments_raw}"
                            )

                            if tool_name == "get_booking_options":
                                try:
                                    args = json.loads(arguments_raw)
                                except Exception as e:
                                    print(f"Failed to parse tool arguments: {e}")
                                    args = {}


                                tool_started_at = time.perf_counter()

                                tool_result = get_booking_options_for_ai(
                                    clinic_id=current_clinic_id,
                                    doctors=current_doctors,
                                    doctor_name=args.get("doctor_name"),
                                    reason=args.get("reason"),
                                    preferred_date_raw=args.get("preferred_date_raw"),
                                    preferred_time_raw=args.get("preferred_time_raw"),
                                    preferred_date_confirmed=bool(
                                        args.get("preferred_date_confirmed")
                                    ),
                                )

                                tool_duration = time.perf_counter() - tool_started_at

                                print(
                                    "Realtime booking tool result | "
                                    f"duration_seconds={tool_duration:.3f} | "
                                    f"args={args} | "
                                    f"result={tool_result}"
                                )

                                # Keep the full internal result for after-call extraction and DB saving.
                                if tool_result.get("ok") and tool_result.get("slots"):
                                    booking_options_history.append(
                                        {
                                            "tool_call_index": len(booking_options_history) + 1,
                                            "doctor_name_requested": args.get("doctor_name"),
                                            "reason": args.get("reason"),
                                            "preferred_date_raw": args.get("preferred_date_raw"),
                                            "preferred_time_raw": args.get("preferred_time_raw"),
                                            "preferred_date_confirmed": bool(
                                                args.get("preferred_date_confirmed")
                                            ),
                                            "slots": tool_result.get("slots") or [],
                                        }
                                    )

                                # Send a sanitized patient-facing version to the Realtime model.
                                patient_facing_tool_result = sanitize_booking_options_for_patient(tool_result)

                                await openai_ws.send(
                                    json.dumps(
                                        {
                                            "type": "conversation.item.create",
                                            "item": {
                                                "type": "function_call_output",
                                                "call_id": tool_call_id,
                                                "output": json.dumps(
                                                    patient_facing_tool_result,
                                                    ensure_ascii=False,
                                                ),
                                            },
                                        }
                                    )
                                )

                                await create_short_audio_response()

                            elif tool_name == "note_booking_request":
                                selected_slot = None

                                if booking_options_history:
                                    last_offer = booking_options_history[-1]
                                    slots = last_offer.get("slots") or []

                                    if slots:
                                        selected_slot = slots[0]
                                        last_offer["accepted_slot"] = selected_slot

                                if selected_slot:
                                    appointment_request_write_needed = True
                                    end_call_requested = True

                                    tool_result = {
                                        "ok": True,
                                        "status": "booking_request_noted",
                                        "message_for_ai": (
                                            "Tell the caller the request is noted and the front desk will confirm."
                                        ),
                                    }

                                    print(
                                        "Booking request completed by workflow | "
                                        f"accepted_slot={selected_slot}, "
                                        f"appointment_request_write_needed={appointment_request_write_needed}, "
                                        f"end_call_requested={end_call_requested}, "
                                        f"current_twilio_call_sid={current_twilio_call_sid}"
                                    )

                                else:
                                    tool_result = {
                                        "ok": False,
                                        "status": "selected_slot_not_found",
                                        "message_for_ai": (
                                            "Say the front desk will contact them to find the best time."
                                        ),
                                    }

                                    print(
                                        "note_booking_request failed | "
                                        f"booking_options_history_count={len(booking_options_history)}"
                                    )

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

                                await create_short_audio_response()
                                if end_call_requested:
                                    await schedule_call_end("booking_request_completed")

                            elif tool_name == "get_faq_answer":
                                try:
                                    args = json.loads(arguments_raw)
                                except Exception as e:
                                    print(f"Failed to parse FAQ arguments: {e}")
                                    args = {}

                                tool_result = get_faq_answer_for_ai(
                                    clinic_id=current_clinic_id,
                                    caller_question=args.get("caller_question"),
                                )

                                print(f"Realtime FAQ tool result: {tool_result}")

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

                                await create_short_audio_response()

                            elif tool_name == "get_working_hours":
                                try:
                                    args = json.loads(arguments_raw)
                                except Exception as e:
                                    print(
                                        f"Failed to parse working hours arguments: {e}"
                                    )
                                    args = {}

                                tool_result = get_working_hours_for_ai(
                                    clinic_id=current_clinic_id,
                                    doctors=current_doctors,
                                    caller_question=args.get("caller_question"),
                                    doctor_name=args.get("doctor_name"),
                                    date_raw=args.get("date_raw"),
                                )

                                print(
                                    f"Realtime working hours tool result: {tool_result}"
                                )

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

                                await create_short_audio_response()

                            elif tool_name == "get_upcoming_appointments":
                                try:
                                    args = json.loads(arguments_raw)
                                except Exception as e:
                                    print(
                                        f"Failed to parse appointment lookup arguments: {e}"
                                    )
                                    args = {}

                                tool_result = get_upcoming_appointments_for_ai(
                                    clinic_id=current_clinic_id,
                                    patient_id=args.get("patient_id"),
                                )

                                print(
                                    f"Realtime appointment lookup result: {tool_result}"
                                )

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

                                await create_short_audio_response()

                            elif tool_name == "cancel_appointment":
                                try:
                                    args = json.loads(arguments_raw)
                                except Exception as e:
                                    print(
                                        f"Failed to parse cancel appointment arguments: {e}"
                                    )
                                    args = {}

                                tool_result = cancel_appointment_for_ai(
                                    clinic_id=current_clinic_id,
                                    patient_id=args.get("patient_id"),
                                    appointment_id=args.get("appointment_id"),
                                )

                                print(
                                    f"Realtime cancel appointment result: {tool_result}"
                                )

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

                                await create_short_audio_response()

                            elif tool_name == "reschedule_appointment":
                                try:
                                    args = json.loads(arguments_raw)
                                except Exception as e:
                                    print(
                                        f"Failed to parse reschedule appointment arguments: {e}"
                                    )
                                    args = {}

                                tool_result = reschedule_appointment_for_ai(
                                    clinic_id=current_clinic_id,
                                    patient_id=args.get("patient_id"),
                                    appointment_id=args.get("appointment_id"),
                                    doctor_id=args.get("doctor_id"),
                                    start_time_iso=args.get("start_time_iso"),
                                    end_time_iso=args.get("end_time_iso"),
                                    call_id=current_call_id,
                                    patient_phone=current_caller_phone,
                                )

                                print(
                                    f"Realtime reschedule appointment result: {tool_result}"
                                )

                                if tool_result.get("ok"):
                                    appointment_request_write_needed = False
                                    end_call_requested = True

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

                                await create_short_audio_response()

                            else:
                                print(f"Unknown realtime tool requested: {tool_name}")

                        elif event_type == "response.done":
                            current_response_id = None

                            track_realtime_response_done(
                                openai_usage_totals,
                                response,
                            )

                            print_usage_summary(
                                "OpenAI event: response.done",
                                openai_usage_totals,
                            )

                            persist_call_openai_usage(
                                call_id=current_call_id,
                                totals=openai_usage_totals,
                                update_call_func=update_call,
                                model=OPENAI_REALTIME_MODEL,
                            )

                            if end_call_requested:
                                print(
                                    "Response done with end_call_requested=True | "
                                    f"current_twilio_call_sid={current_twilio_call_sid}"
                                )
                                await schedule_call_end("workflow_completed")

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