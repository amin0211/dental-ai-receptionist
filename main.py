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
    appointment_draft = {}

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
                        "You are a friendly, concise AI receptionist for Westview Dental in Vancouver, BC. "

                        "Language rule: detect the caller's language and respond in the same language. "
                        "If the caller speaks Persian/Farsi, respond naturally in Persian/Farsi. "
                        "If the caller speaks English, respond naturally in English. "
                        "Do not switch languages unless the caller switches or asks you to. "

                        "Your job is to help callers with appointment requests, clinic hours, location questions, "
                        "and urgent dental concerns. "
                        "Keep every response short and natural. "
                        "Ask only one question at a time. "
                        "Never ask for multiple details in one sentence. "

                        "For appointment requests, collect information step by step in this exact order: "
                        "1. full name, "
                        "2. reason for visit, "
                        "3. preferred date, "
                        "4. preferred time. "

                        "For Persian/Farsi callers, collect sensitive details in very small pieces because phone transcription may be imperfect. "
                        "Ask for the full name first. "
                        "After the caller gives the name, repeat only the name back in the caller's language and ask if it is correct. "
                        "If the caller says it is not correct or corrects you, ask them to repeat the name slowly. "

                        "Then ask for the reason for the visit separately. "
                        "Do not assume the reason from your own wording. "
                        "Use only what the caller says as the reason. "

                        "Then ask for the preferred date only. "
                        "Do not ask for date and time together. "
                        "After the caller gives the date, repeat only the date back and ask if it is correct. "
                        "If the caller says it is not correct or corrects you, ask them to repeat the date slowly. "

                        "Only after the date is confirmed, ask for the preferred time separately. "
                        "After the caller gives the time, repeat only the time back and ask if it is correct. "
                        "If the caller says it is not correct or corrects you, ask them to repeat the time slowly. "

                        "For English callers, follow the same step-by-step process: "
                        "full name, reason, preferred date, preferred time. "
                        "Repeat back the date and time separately and ask for confirmation before saying the request has been noted. "

                        "Do not claim the appointment is confirmed. "
                        "Only say the appointment request has been noted and the front desk will contact them to confirm. "

                        "Do not say the appointment request has been captured until the caller has confirmed the preferred date and preferred time, "
                        "or until they clearly say they do not have a preference. "

                        "Do not read the caller's full phone number out loud. "
                        "If needed, ask whether the number they are calling from is the best callback number. "

                        "For urgent dental concerns such as severe swelling, uncontrolled bleeding, facial trauma, or trouble breathing, "
                        "advise the caller to seek emergency medical care immediately and tell them the clinic team will be notified. "

                        "Do not interrupt the caller. Wait until the caller clearly finishes speaking before responding."

                        "Use the save_appointment_draft tool whenever the caller provides or confirms appointment information. "
                        "For name and reason, call the tool after the caller provides the value. "
                        "For date and time, call the tool only after you repeat the value back and the caller confirms it. "
                        "Do not call the tool with unconfirmed date or time unless the caller clearly says they have no preference. "

                    ),

                    "output_modalities": ["audio"],
                    "tools": [
                        {
                            "type": "function",
                            "name": "save_appointment_draft",
                            "description": (
                                "Use this tool to save structured appointment details during the call. "
                                "Call it only after the caller provides or confirms a piece of information. "
                                "For date and time, call it only after repeating the understood value back to the caller "
                                "and the caller confirms it is correct."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "patient_name": {
                                        "type": ["string", "null"],
                                        "description": "The caller's full name, only if provided or confirmed."
                                    },
                                    "reason": {
                                        "type": ["string", "null"],
                                        "description": "The reason for visit, such as filling, checkup, cleaning, tooth pain, or the original phrase."
                                    },
                                    "preferred_date_raw": {
                                        "type": ["string", "null"],
                                        "description": "The preferred appointment date as understood and confirmed, e.g. June 21."
                                    },
                                    "preferred_time_raw": {
                                        "type": ["string", "null"],
                                        "description": "The preferred appointment time as understood and confirmed, e.g. 3 PM."
                                    },
                                    "date_confirmed": {
                                        "type": "boolean",
                                        "description": "True only if the caller confirmed the date."
                                    },
                                    "time_confirmed": {
                                        "type": "boolean",
                                        "description": "True only if the caller confirmed the time."
                                    },
                                    "language": {
                                        "type": ["string", "null"],
                                        "description": "Caller language, such as fa or en."
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "description": "Confidence from 0 to 1."
                                    },
                                    "notes": {
                                        "type": ["string", "null"],
                                        "description": "Short note about uncertainty, corrections, or transcription issues."
                                    }
                                },
                                "required": [
                                    "patient_name",
                                    "reason",
                                    "preferred_date_raw",
                                    "preferred_time_raw",
                                    "date_confirmed",
                                    "time_confirmed",
                                    "language",
                                    "confidence",
                                    "notes"
                                ],
                                "additionalProperties": False
                            },
                        }
                    ],
                    "tool_choice": "auto",                    
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
                                "threshold": 0.75,
                                "prefix_padding_ms": 500,
                                "silence_duration_ms": 1200,
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

                                service_match = match_service_from_transcript(
                                    current_clinic_id,
                                    caller_only_transcript,
                                )

                                appointment_details = extract_appointment_details_from_transcript(
                                    full_transcript
                                )
                                
                                print(f"Final appointment draft: {appointment_draft}")
                                
                                save_call_extraction(
                                    clinic_id=current_clinic_id,
                                    call_id=current_call_id,
                                    raw_transcript=full_transcript,
                                    cleaned_transcript=None,
                                    detected_language=None,
                                    patient_name=appointment_details["patient_name"],
                                    service_category=service_match["category_name"] if service_match else None,
                                    canonical_reason=service_match["canonical_reason"] if service_match else None,
                                    preferred_time_raw=appointment_details["preferred_time"],
                                    preferred_datetime=None,
                                    urgency=service_match["default_urgency"] if service_match else "normal",
                                    confidence=None,
                                    extraction_notes="Initial extraction using DB keyword match and transcript context.",
                                )

                                should_create_request = (
                                    (service_match and service_match["creates_appointment_request"])
                                    or bool(appointment_draft.get("reason"))
                                )

                                if should_create_request:
                                    create_appointment_request(
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
                                            appointment_draft.get("preferred_time_raw")
                                            or appointment_details["preferred_time"]
                                        ),
                                        urgency=service_match["default_urgency"] if service_match else "normal",
                                        status="new",
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
                nonlocal stream_sid, transcript_parts, ai_transcript_buffer, appointment_draft

                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)
                        event_type = response.get("type")

                        if event_type in ["session.created", "session.updated"]:
                            print(f"OpenAI event: {event_type}")

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

                        elif event_type in [
                            "response.function_call_arguments.done",
                            "response.output_item.done",
                            "conversation.item.created",
                        ]:
                            item = response.get("item") or {}

                            function_name = response.get("name") or item.get("name")
                            arguments_text = response.get("arguments") or item.get("arguments")
                            call_id = response.get("call_id") or item.get("call_id")

                            item_type = item.get("type")

                            if item_type == "function_call":
                                function_name = item.get("name")
                                arguments_text = item.get("arguments")
                                call_id = item.get("call_id")

                            if function_name == "save_appointment_draft" and arguments_text:
                                try:
                                    tool_args = json.loads(arguments_text)

                                    for key, value in tool_args.items():
                                        if value is not None:
                                            appointment_draft[key] = value

                                    print(f"Updated appointment draft from tool call: {appointment_draft}")

                                    if call_id:
                                        await openai_ws.send(
                                            json.dumps(
                                                {
                                                    "type": "conversation.item.create",
                                                    "item": {
                                                        "type": "function_call_output",
                                                        "call_id": call_id,
                                                        "output": json.dumps(
                                                            {
                                                                "ok": True,
                                                                "saved": True,
                                                            }
                                                        ),
                                                    },
                                                }
                                            )
                                        )

                                        await openai_ws.send(
                                            json.dumps(
                                                {
                                                    "type": "response.create",
                                                    "response": {
                                                        "instructions": (
                                                            "Briefly continue the phone conversation naturally. "
                                                            "Do not mention internal tools or databases."
                                                        )
                                                    },
                                                }
                                            )
                                        )

                                except Exception as e:
                                    print(f"Error handling save_appointment_draft tool call: {e}")

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
    preferred_time = None

    lines = transcript.splitlines()

    for i, line in enumerate(lines):
        clean_line = line.strip()

        if not clean_line.startswith("Caller:"):
            continue

        caller_text = clean_line.replace("Caller:", "").strip()
        if not caller_text:
            continue

        previous_line = lines[i - 1].lower() if i > 0 else ""

        # Name: caller response after AI asks for full name
        if patient_name is None:
            if (
                "full name" in previous_line
                or "your name" in previous_line
                or "name, please" in previous_line
                or "اسم" in previous_line
                or "نام" in previous_line
                or "اسم کامل" in previous_line
                or "نام کامل" in previous_line
                or "اسمتون" in previous_line
                or "نامتون" in previous_line                
            ):
                if len(caller_text.split()) <= 6:
                    patient_name = caller_text

        # Preferred time: caller response after AI asks for day/time/preferred time
        if preferred_time is None:
            if (
                "what day" in previous_line
                or "what time" in previous_line
                or "preferred day" in previous_line
                or "preferred time" in previous_line
                or "day or time" in previous_line
                or "works best" in previous_line
                or "چه روزی" in previous_line
                or "چه ساعتی" in previous_line
                or "چه زمانی" in previous_line
                or "زمان" in previous_line
                or "ساعت" in previous_line
                or "کی" in previous_line
                or "چه موقع" in previous_line
                or "چه روز" in previous_line
                or "چه ساعت" in previous_line
                or "زمانی مدنظرتونه" in previous_line
                or "ساعت مدنظرتون" in previous_line                
            ):
                preferred_time = caller_text

    return {
        "patient_name": patient_name,
        "preferred_time": preferred_time,
    }
