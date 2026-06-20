import os
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import Response
from supabase import create_client, Client

from fastapi import WebSocket, WebSocketDisconnect
import json

import asyncio
import websockets

from supabase_service import (
    supabase,
    normalize_phone,
    find_clinic_by_twilio_number,
    save_call_to_db,
    create_appointment_request,
    update_appointment_request,
    update_call,
    match_service_from_transcript,
    save_call_extraction,
)

app = FastAPI()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_REALTIME_MODEL = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2")


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

            session_update = {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "model": OPENAI_REALTIME_MODEL,
                    "instructions": (
                        "You are a concise AI receptionist for Westview Dental in Vancouver, BC. "
                        "Start in neutral English unless the caller clearly speaks another language first. "
                        "Reply in the caller's clearly detected language. "
                        "If the caller clearly speaks Persian/Farsi at any point, switch to Persian/Farsi and continue in Persian/Farsi. "
                        "If the caller clearly asks to use another language, switch to that language. "
                        "If the caller's speech is mixed, garbled, or unclear, do not switch languages based on that unclear fragment. "
                        "When speech is unclear, stay in the last clearly established language and ask the caller to repeat clearly. "
                        "Do not switch languages because of one random foreign-looking transcript fragment. "
                        "Keep every reply short. Ask exactly one question at a time. "

                        "For appointment booking, collect fields in this exact order: "
                        "patient_name, reason, preferred_date_raw, preferred_time_raw. "
                        "Do not skip steps. Never ask for more than one field in the same reply. "
                        "Never ask for date and time together. "

                        "Every non-final assistant reply must contain exactly one sentence, and that sentence must be a direct question. "
                        "The final reply may be one short statement, but only after the required appointment details are collected. "
                        "Never say any acknowledgement, filler, transition, or status sentence before asking the question. "
                        "Do not use filler, acknowledgement, transition, or status phrases in any language. "
                        "Do not tell the caller that you are checking, reviewing, saving, registering, storing, confirming internally, or moving to the next step. "
                        "Do not say anything equivalent to: okay, alright, one moment, please wait, let me check, I will check, let me save that, I will save that, next step, I will ask the next question now. "

                        "If the caller's answer is garbled, mixed-language, unrelated, or low-confidence, do not convert it into a name, date, time, or reason. "
                        "Ask the same field again in the last clearly established language. "
                        "Never turn unclear audio into a likely name, date, time, or reason. "
                        "Never turn unclear audio into a likely date such as next Tuesday, next Monday, April 22, April 15, or a likely time such as 3 PM or 9:30 AM. "
                        "Random words, foreign-language fragments, unrelated words, or unclear sounds are not confirmation. "
                        "Only clear yes/no answers in the caller's language count as confirmation. "

                        "For patient_name, ask for the full name. "
                        "If the caller gives a clear name, repeat only the understood name and ask if it is correct. "
                        "If the caller clearly confirms the repeated name, move to reason. "
                        "If the caller gives a clear correction, use the corrected name and move to reason. "
                        "If the caller says no without a clear correction, ask for the full name again. "
                        "If the name remains unclear after two attempts, continue to reason and let the front desk confirm the name later. "

                        "For reason, ask only why they want the dental visit. "
                        "If the reason is understandable, accept it and move to preferred_date_raw. "
                        "Do not ask for confirmation of the reason unless it is unclear. "
                        "If the reason is unclear, ask why they want the dental visit again. "
                        "If the reason remains unclear after two attempts, continue to preferred_date_raw and let the front desk clarify the reason later. "

                        "For preferred_date_raw, ask only for the preferred date. "
                        "After the caller gives a clear date, repeat only the understood date and ask if it is correct. "
                        "The date is not collected until the caller clearly confirms it after you repeat it. "
                        "If the caller says no and provides a corrected date, discard the old date, repeat only the corrected date, and ask if it is correct. "
                        "If the caller says no without a clear correction, discard the old date and ask for the preferred date again. "
                        "If the date remains unclear after two attempts, continue to preferred_time_raw and let the front desk confirm the date later. "

                        "For preferred_time_raw, ask only for the preferred time. "
                        "After the caller gives a clear time, repeat only the understood time and ask if it is correct. "
                        "The time is not collected until the caller clearly confirms it after you repeat it. "
                        "If the caller says no and provides a corrected time, discard the old time, repeat only the corrected time, and ask if it is correct. "
                        "If the caller says no without a clear correction, discard the old time and ask for the preferred time again. "
                        "If the time remains unclear after two attempts, finish politely and say the front desk will contact them to confirm the missing details. "

                        "Never say the request has been noted unless at least patient_name, reason, preferred_date_raw, and preferred_time_raw have been attempted. "
                        "If some details are unclear after repeated attempts, say the front desk will contact them to confirm the missing details. "
                        "After all required fields have been attempted, say the request has been noted and the front desk will contact them to confirm. "
                        "Never say the appointment is confirmed. "

                        "For severe swelling, uncontrolled bleeding, facial trauma, or trouble breathing, advise emergency medical care immediately."
                    ),

                    "output_modalities": ["audio"],
                
                    "audio": {
                        "input": {
                            "format": {
                                "type": "audio/pcmu",
                            },
                            "transcription": {
                                "model": "gpt-4o-transcribe",#"gpt-4o-mini-transcribe",
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
                },
            }

            await openai_ws.send(json.dumps(session_update))
            print("Sent OpenAI session.update")


            async def receive_from_twilio():
                nonlocal stream_sid, current_call_id, current_clinic_id, current_caller_phone, transcript_parts

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

                                appointment_details = extract_appointment_details_from_transcript(full_transcript)

                                print(f"Final extracted appointment details: {appointment_details}")

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
                                date_confirmed = appointment_details.get("date_confirmed")
                                time_confirmed = appointment_details.get("time_confirmed")

                                save_call_extraction(
                                    clinic_id=current_clinic_id,
                                    call_id=current_call_id,
                                    raw_transcript=full_transcript,
                                    cleaned_transcript=appointment_details.get("notes"),
                                    detected_language=appointment_details.get("language"),
                                    patient_name=patient_name,
                                    service_category=service_match["category_name"] if service_match else None,
                                    canonical_reason=reason,
                                    preferred_time_raw=preferred_time_raw,
                                    preferred_datetime=None,
                                    urgency=service_match["default_urgency"] if service_match else "normal",
                                    confidence=appointment_details.get("confidence"),
                                    extraction_notes=json.dumps(appointment_details, ensure_ascii=False),
                                    preferred_date_raw=preferred_date_raw,
                                    preferred_date_confirmed=date_confirmed,
                                    preferred_time_confirmed=time_confirmed,
                                )

                                should_create_request = bool(reason or patient_name or preferred_date_raw or preferred_time_raw)

                                if should_create_request:
                                    preferred_time_combined = (
                                        ((preferred_date_raw or "") + " " + (preferred_time_raw or "")).strip()
                                        or None
                                    )

                                    appointment_request = create_appointment_request(
                                        clinic_id=current_clinic_id,
                                        call_id=current_call_id,
                                        patient_phone=current_caller_phone,
                                        patient_name=patient_name,
                                        reason=reason,
                                        preferred_time=preferred_time_combined,
                                        urgency=service_match["default_urgency"] if service_match else "normal",
                                        status="new",
                                    )

                                    if appointment_request:
                                        update_appointment_request(
                                            appointment_request["id"],
                                            {
                                                "preferred_date_raw": preferred_date_raw,
                                                "preferred_time_raw": preferred_time_raw,
                                                "preferred_date_confirmed": date_confirmed,
                                                "preferred_time_confirmed": time_confirmed,
                                            },
                                        )

                                    print(
                                        "Realtime appointment request created from transcript extraction: "
                                        f"service={service_match}, details={appointment_details}"
                                    )
                                else:
                                    print(f"No appointment request created. service_match={service_match}, details={appointment_details}")

                                service_match_input = caller_only_transcript



                                service_match = match_service_from_transcript(
                                    current_clinic_id,
                                    service_match_input,
                                )

                                appointment_details = extract_appointment_details_from_transcript(
                                    full_transcript
                                )
                                
                                print(f"Final appointment draft: {appointment_draft}")
                                
                                save_call_extraction(
                                    clinic_id=current_clinic_id,
                                    call_id=current_call_id,
                                    raw_transcript=full_transcript,
                                    cleaned_transcript=appointment_draft.get("notes"),
                                    detected_language=appointment_draft.get("language"),
                                    patient_name=appointment_draft.get("patient_name") or appointment_details["patient_name"],
                                    service_category=service_match["category_name"] if service_match else None,
                                    canonical_reason=(
                                        service_match["canonical_reason"]
                                        if service_match
                                        else appointment_draft.get("reason")
                                    ),
                                    preferred_time_raw=(
                                        appointment_draft.get("preferred_time_raw")
                                        or appointment_details["preferred_time"]
                                    ),
                                    preferred_datetime=None,
                                    urgency=service_match["default_urgency"] if service_match else "normal",
                                    confidence=appointment_draft.get("confidence"),
                                    extraction_notes=json.dumps(appointment_draft, ensure_ascii=False),
                                    preferred_date_raw=appointment_draft.get("preferred_date_raw"),
                                    preferred_date_confirmed=appointment_draft.get("date_confirmed"),
                                    preferred_time_confirmed=appointment_draft.get("time_confirmed"),
                                )


                                should_create_request = (
                                    (service_match and service_match["creates_appointment_request"])
                                    or bool(appointment_draft.get("reason"))
                                )



                                if should_create_request:
                                    appointment_request = create_appointment_request(
                                        clinic_id=current_clinic_id,
                                        call_id=current_call_id,
                                        patient_phone=current_caller_phone,
                                        patient_name=appointment_draft.get("patient_name") or appointment_details["patient_name"],
                                        reason=(
                                            service_match["canonical_reason"]
                                            if service_match
                                            else appointment_draft.get("reason")
                                        ),
                                        preferred_time=(
                                            (
                                                (appointment_draft.get("preferred_date_raw") or "") + " " +
                                                (appointment_draft.get("preferred_time_raw") or "")
                                            ).strip()
                                            or appointment_details["preferred_time"]
                                        ),
                                        urgency=service_match["default_urgency"] if service_match else "normal",
                                        status="new",
                                    )

                                    if appointment_request:
                                        update_appointment_request(
                                            appointment_request["id"],
                                            {
                                                "preferred_date_raw": appointment_draft.get("preferred_date_raw"),
                                                "preferred_time_raw": appointment_draft.get("preferred_time_raw"),
                                                "preferred_date_confirmed": appointment_draft.get("date_confirmed"),
                                                "preferred_time_confirmed": appointment_draft.get("time_confirmed"),
                                            },
                                        )

                                    print(
                                        "Realtime appointment request created from structured draft: "
                                        f"service={service_match}, details={appointment_details}, draft={appointment_draft}"
                                    )
                                else:
                                    print(f"No appointment request created. service_match={service_match}")

                                    
                            await openai_ws.close()
                            break

                except WebSocketDisconnect:
                    print("Twilio WebSocket disconnected")
                    await openai_ws.close()

                except Exception as e:
                    print(f"Twilio receive error: {e}")
                    await openai_ws.close()


            async def receive_from_openai():
                nonlocal stream_sid, transcript_parts, ai_transcript_buffer


                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)
                        event_type = response.get("type")

                        if event_type in ["session.created", "session.updated"]:
                            print(f"OpenAI event: {event_type}")

                        elif event_type == "response.created":
                            response_active = True
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


                        elif event_type == "response.done":
                            response_active = False
                            print("OpenAI event: response.done")

                        elif event_type == "error":
                            response_active = False
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
                <Gather input="speech" action="/twilio/collect-name?appointment_id={appointment_id}" method="POST" timeout="8" speechTimeout="auto" language="en-US">
                    <Say voice="alice" language="en-US">
                        Thank you. I can help create an appointment request.
                        May I have your full name?
                    </Say>
                </Gather>

                <Redirect method="POST">/twilio/collect-name?appointment_id={appointment_id}</Redirect>
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



@app.post("/twilio/collect-name")
async def collect_name(request: Request):
    form = await request.form()

    appointment_id = request.query_params.get("appointment_id")
    retry = int(request.query_params.get("retry", "0"))

    patient_name = form.get("SpeechResult", "")

    if not patient_name:
        if retry < 2:
            next_retry = retry + 1

            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/twilio/collect-name?appointment_id={appointment_id}&amp;retry={next_retry}" method="POST" timeout="8" speechTimeout="auto" language="en-US">
        <Say voice="alice" language="en-US">
            Sorry, I did not catch your name. Please say your full name again.
        </Say>
    </Gather>

    <Redirect method="POST">/twilio/collect-name?appointment_id={appointment_id}&amp;retry={next_retry}</Redirect>
</Response>
"""
            return Response(content=twiml, media_type="application/xml")

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/twilio/collect-time?appointment_id={appointment_id}" method="POST" timeout="8" speechTimeout="auto" language="en-US">
        <Say voice="alice" language="en-US">
            That is okay. The front desk can confirm your name later.
            What day or time would you prefer for this appointment?
        </Say>
    </Gather>

    <Redirect method="POST">/twilio/collect-time?appointment_id={appointment_id}</Redirect>
</Response>
"""
        return Response(content=twiml, media_type="application/xml")

    if appointment_id:
        update_appointment_request(
            appointment_id=appointment_id,
            updates={"patient_name": patient_name},
        )

    safe_name = xml_escape(patient_name)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/twilio/collect-time?appointment_id={appointment_id}" method="POST" timeout="8" speechTimeout="auto" language="en-US">
        <Say voice="alice" language="en-US">
            Thank you, {safe_name}. What day or time would you prefer for this appointment?
        </Say>
    </Gather>

    <Redirect method="POST">/twilio/collect-time?appointment_id={appointment_id}</Redirect>
</Response>
"""
    return Response(content=twiml, media_type="application/xml")


@app.post("/twilio/collect-time")
async def collect_time(request: Request):
    form = await request.form()

    appointment_id = request.query_params.get("appointment_id")
    retry = int(request.query_params.get("retry", "0"))

    preferred_time = form.get("SpeechResult", "")

    if not preferred_time:
        if retry < 2:
            next_retry = retry + 1

            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/twilio/collect-time?appointment_id={appointment_id}&amp;retry={next_retry}" method="POST" timeout="8" speechTimeout="auto" language="en-US">
        <Say voice="alice" language="en-US">
            Sorry, I did not catch the preferred time. Please say the day or time you would prefer.
        </Say>
    </Gather>

    <Redirect method="POST">/twilio/collect-time?appointment_id={appointment_id}&amp;retry={next_retry}</Redirect>
</Response>
"""
            return Response(content=twiml, media_type="application/xml")

        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="en-US">
        That is okay. The front desk will contact you to confirm a suitable appointment time.
        Goodbye.
    </Say>
</Response>
"""
        return Response(content=twiml, media_type="application/xml")

    if appointment_id:
        update_appointment_request(
            appointment_id=appointment_id,
            updates={"preferred_time": preferred_time},
        )

    safe_time = xml_escape(preferred_time)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="en-US">
        Thank you. I captured your preferred time as {safe_time}.
        The front desk will contact you to confirm the appointment.
        Goodbye.
    </Say>
</Response>
"""
    return Response(content=twiml, media_type="application/xml")


def extract_appointment_details_from_transcript(transcript: str) -> dict:
    patient_name = None
    reason = None
    preferred_date_raw = None
    preferred_time_raw = None
    date_confirmed = False
    time_confirmed = False
    language = None
    confidence = 0.5
    notes = []

    lines = [line.strip() for line in transcript.splitlines() if line.strip()]

    last_ai_question = None
    pending_confirmation_type = None
    pending_confirmation_value = None

    yes_words = {
        "yes", "yeah", "yep", "correct", "right", "ok", "okay",
        "بله", "آره", "اره", "درسته", "صحیح", "تایید", "تأیید",
        "vale", "vvale", "alé", "ale"
    }

    no_words = {
        "no", "nope", "nah", "wrong", "incorrect",
        "نه", "نخیر", "نه خیر", "غلطه", "اشتباهه",
        "na", "no es"
    }

    def normalize_text(text: str) -> str:
        return (
            text.strip()
            .lower()
            .replace("؟", "")
            .replace("?", "")
            .replace(".", "")
            .replace(",", "")
            .replace("«", "")
            .replace("»", "")
            .replace('"', "")
            .replace("'", "")
        )

    def is_yes(text: str) -> bool:
        t = normalize_text(text)
        return any(word in t.split() or word == t for word in yes_words)

    def is_no(text: str) -> bool:
        t = normalize_text(text)
        return any(word in t for word in no_words)

    def looks_garbled(text: str) -> bool:
        t = normalize_text(text)

        if len(t) <= 1:
            return True

        # Mostly random Latin fragments from bad transcription
        latin_chars = sum(1 for ch in t if "a" <= ch <= "z")
        total_letters = sum(1 for ch in t if ch.isalpha())

        if total_letters >= 3 and latin_chars / max(total_letters, 1) > 0.7:
            common_clear_words = [
                "may", "june", "july", "april", "march", "monday", "tuesday",
                "wednesday", "thursday", "friday", "morning", "afternoon",
                "cleaning", "checkup", "pain", "filling"
            ]
            if not any(word in t for word in common_clear_words):
                return True

        return False

    def extract_quoted_value(ai_text: str) -> str | None:
        if "«" in ai_text and "»" in ai_text:
            start = ai_text.find("«") + 1
            end = ai_text.find("»", start)
            if end > start:
                return ai_text[start:end].strip()

        if '"' in ai_text:
            parts = ai_text.split('"')
            if len(parts) >= 3:
                return parts[1].strip()

        return None

    for i, line in enumerate(lines):
        if line.startswith("AI:"):
            ai_text = line.replace("AI:", "", 1).strip()
            ai_lower = ai_text.lower()
            last_ai_question = ai_text

            quoted_value = extract_quoted_value(ai_text)

            # Detect confirmation questions
            if quoted_value:
                if (
                    "name" in ai_lower
                    or "full name" in ai_lower
                    or "correct" in ai_lower
                    or "نام" in ai_text
                    or "اسم" in ai_text
                    or "صحیح" in ai_text
                    or "درست" in ai_text
                ):
                    # This could be name/date/time; infer from content and previous flow
                    if any(month in ai_lower for month in ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]):
                        pending_confirmation_type = "date"
                    elif any(token in ai_lower for token in ["am", "pm", "morning", "afternoon", "evening", "o'clock", "ساعت", "صبح", "ظهر", "بعدازظهر", "عصر"]):
                        pending_confirmation_type = "time"
                    elif preferred_date_raw is None and ("date" in ai_lower or "تاریخ" in ai_text):
                        pending_confirmation_type = "date"
                    elif preferred_time_raw is None and ("time" in ai_lower or "ساعت" in ai_text):
                        pending_confirmation_type = "time"
                    elif patient_name is None:
                        pending_confirmation_type = "name"
                    else:
                        pending_confirmation_type = "unknown"

                    pending_confirmation_value = quoted_value

            continue

        if not line.startswith("Caller:"):
            continue

        caller_text = line.replace("Caller:", "", 1).strip()
        caller_lower = caller_text.lower()

        if not caller_text:
            continue

        if language is None:
            if any("\u0600" <= ch <= "\u06FF" for ch in caller_text):
                language = "fa"
            else:
                language = "unknown"

        # Handle yes/no confirmation
        if pending_confirmation_type and pending_confirmation_value:
            if is_yes(caller_text):
                if pending_confirmation_type == "name":
                    patient_name = pending_confirmation_value
                elif pending_confirmation_type == "date":
                    preferred_date_raw = pending_confirmation_value
                    date_confirmed = True
                elif pending_confirmation_type == "time":
                    preferred_time_raw = pending_confirmation_value
                    time_confirmed = True

                pending_confirmation_type = None
                pending_confirmation_value = None
                continue

            if is_no(caller_text):
                notes.append(
                    f"Caller rejected {pending_confirmation_type}: {pending_confirmation_value}"
                )
                pending_confirmation_type = None
                pending_confirmation_value = None
                continue

        previous_ai = last_ai_question or ""
        previous_ai_lower = previous_ai.lower()

        if looks_garbled(caller_text):
            notes.append(f"Possible garbled caller text: {caller_text}")
            continue

        # Name candidate
        if patient_name is None and (
            "full name" in previous_ai_lower
            or "your name" in previous_ai_lower
            or "name" in previous_ai_lower
            or "نام" in previous_ai
            or "اسم" in previous_ai
        ):
            if len(caller_text.split()) <= 6:
                patient_name = caller_text
            continue

        # Reason candidate
        if reason is None and (
            "reason" in previous_ai_lower
            or "visit" in previous_ai_lower
            or "dental" in previous_ai_lower
            or "مراجعه" in previous_ai
            or "دلیل" in previous_ai
            or "چرا" in previous_ai
        ):
            reason = caller_text
            continue

        # Date candidate
        if preferred_date_raw is None and (
            "date" in previous_ai_lower
            or "day" in previous_ai_lower
            or "when" in previous_ai_lower
            or "تاریخ" in previous_ai
            or "چه روز" in previous_ai
            or "چه زمانی" in previous_ai
        ):
            preferred_date_raw = caller_text
            continue

        # Time candidate
        if preferred_time_raw is None and (
            "time" in previous_ai_lower
            or "hour" in previous_ai_lower
            or "ساعت" in previous_ai
        ):
            preferred_time_raw = caller_text
            continue

    filled_count = sum(
        1 for value in [patient_name, reason, preferred_date_raw, preferred_time_raw]
        if value
    )

    confidence = 0.35 + (filled_count * 0.12)

    if date_confirmed:
        confidence += 0.08

    if time_confirmed:
        confidence += 0.08

    confidence = min(confidence, 0.9)

    if notes:
        confidence = min(confidence, 0.65)

    return {
        "patient_name": patient_name,
        "reason": reason,
        "preferred_date_raw": preferred_date_raw,
        "preferred_time_raw": preferred_time_raw,
        "date_confirmed": date_confirmed,
        "time_confirmed": time_confirmed,
        "language": language or "unknown",
        "confidence": confidence,
        "notes": "; ".join(notes) if notes else None,
    }