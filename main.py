import os
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import Response
from supabase import create_client, Client

from config import PUBLIC_WS_URL
from realtime_routes import router as realtime_router

from supabase_service import (
    normalize_phone,
    find_clinic_by_twilio_number,
    save_call_to_db,
    create_appointment_request,
    get_active_doctors_for_clinic,
    get_booking_options_for_ai,
)

app = FastAPI()
app.include_router(realtime_router)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


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
) -> Response:
    safe_caller = xml_escape(normalize_phone(caller_phone))
    safe_to = xml_escape(normalize_phone(to_number))
    safe_call_sid = xml_escape(call_sid or "")

    stream_url = f"{PUBLIC_WS_URL}/twilio/realtime"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
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
# Main Twilio voice webhook
# ---------------------------------------------------------------------

@app.post("/twilio/voice")
async def twilio_voice(request: Request):
    print("[VOICE_START] /twilio/voice received | routing_to=realtime")

    form = await request.form()

    caller = normalize_phone(form.get("From"))
    to_number = normalize_phone(form.get("To"))
    call_sid = form.get("CallSid") or ""

    print(
        f"[VOICE_START_REALTIME] call_sid={call_sid} "
        f"from={caller} to={to_number}"
    )

    return twiml_connect_realtime(
        caller_phone=caller,
        to_number=to_number,
        call_sid=call_sid,
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
        "mode": "realtime_primary",
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