import os
from urllib.parse import urlparse
import json
import asyncio

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
)

app = FastAPI()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_REALTIME_MODEL = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2")
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


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
                "You are a concise AI receptionist for Westview Dental in Vancouver, BC. "

                "Start in neutral English unless the caller clearly speaks another language first. "
                "Reply in the caller's clearly detected language. "
                "If the caller clearly speaks Persian/Farsi at any point, switch to Persian/Farsi and continue in Persian/Farsi. "
                "If the caller clearly asks to use another language, switch to that language. "
                "If the caller's speech is mixed, garbled, or unclear, do not switch languages based on that unclear fragment. "
                "When speech is unclear, stay in the last clearly established language and ask the caller to repeat clearly. "
                "Do not switch languages because of one random foreign-looking transcript fragment. "

                "Keep every reply short. Ask exactly one question at a time. "
                "Every non-final assistant reply must contain exactly one sentence, and that sentence must be a direct question. "
                "Never ask for more than one field in the same reply. "
                "Do not ask for the patient's name. "

                "Never say any acknowledgement, filler, transition, or status sentence before asking the question. "
                "Do not use filler, acknowledgement, transition, or status phrases in any language. "
                "Do not say anything equivalent to: okay, alright, one moment, please wait, let me check, I will check, let me save that, I will save that, next step, I will ask the next question now. "

                "For appointment booking, do not force the caller to choose a doctor first. "
                "If the caller already mentions a doctor, remember that doctor preference. "
                "If the caller does not mention a doctor, ask the reason for the dental visit first. "
                "For reason, ask only why they want the dental visit. "
                "If the reason is understandable, accept it. "
                "Do not ask for confirmation of the reason unless it is unclear. "
                "If the reason is unclear, ask why they want the dental visit again. "

                "After the dental reason is clear, use the get_booking_options tool to find appointment options. "
                "The booking tool uses the treatment duration, eligible doctors, recurring doctor availability, and calendar events from the clinic database. "
                "If the caller already mentioned a doctor, include that doctor name in the tool call. "
                "If the caller did not mention a doctor, pass doctor_name as null. "

                "If the caller gives a preferred date, repeat only the understood date and ask if it is correct before using that date for slot search. "
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


def xml_escape(value: str | None) -> str:
    if not value:
        return ""

    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


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


@app.post("/twilio/voice")
async def twilio_voice(request: Request):
    form = await request.form()

    caller = xml_escape(normalize_phone(form.get("From")))
    to_number = xml_escape(normalize_phone(form.get("To")))
    call_sid = xml_escape(form.get("CallSid") or "")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="en-US">
        Connecting you to the AI receptionist now.
    </Say>
    <Connect>
        <Stream url="wss://web-production-18008.up.railway.app/twilio/realtime">
            <Parameter name="caller_phone" value="{caller}" />
            <Parameter name="to_number" value="{to_number}" />
            <Parameter name="call_sid" value="{call_sid}" />
        </Stream>
    </Connect>
</Response>
"""

    return Response(content=twiml, media_type="application/xml")


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
            appointment_id = appointment_request["id"]

            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="en-US">
        Thank you. I captured your request and the front desk will contact you to confirm.
    </Say>
</Response>
"""

            return Response(content=twiml, media_type="application/xml")

        message = """
        Thank you. I heard that you need help with an appointment.
        I captured your request and the front desk will follow up with you.
        """

    elif intent == "hours_location":
        message = """
        Westview Dental is open Monday to Friday from 9 AM to 5 PM.
        The clinic is located in Vancouver, British Columbia.
        """

    elif intent == "urgent":
        message = """
        I am sorry you are dealing with that.
        I heard that this may be an urgent dental concern.
        If you are experiencing severe swelling, uncontrolled bleeding, facial trauma, or trouble breathing,
        please seek emergency medical care immediately.
        I will mark this as urgent for the clinic team.
        """

    else:
        message = """
        Thank you. I captured your message.
        I will send this to the front desk for follow up.
        """

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="en-US">
        {message}
    </Say>
</Response>
"""

    return Response(content=twiml, media_type="application/xml")


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
        model=os.environ.get("OPENAI_EXTRACTION_MODEL", "gpt-4.1-mini"),
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