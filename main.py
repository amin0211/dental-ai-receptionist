import os
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import Response
from supabase import create_client, Client

app = FastAPI()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


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


def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    return phone.strip()


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


def find_clinic_by_twilio_number(to_number: str):
    if not supabase:
        print("Supabase client is not initialized")
        return None

    try:
        print(f"Looking up clinic for To number: {to_number}")

        result = (
            supabase.table("clinics")
            .select("*")
            .eq("phone_number", to_number)
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
    speech_result: str,
    confidence: str | None,
    intent: str,
    urgency: str,
    summary: str,
):
    if not supabase:
        print("Supabase client is not initialized")
        return None

    try:
        payload = {
            "clinic_id": clinic_id,
            "twilio_call_sid": twilio_call_sid,
            "caller_phone": caller_phone,
            "speech_result": speech_result,
            "confidence": confidence,
            "intent": intent,
            "urgency": urgency,
            "summary": summary,
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
    reason: str,
    urgency: str,
):
    if not supabase:
        print("Supabase client is not initialized")
        return None

    try:
        payload = {
            "clinic_id": clinic_id,
            "call_id": call_id,
            "patient_phone": patient_phone,
            "reason": reason,
            "urgency": urgency,
            "status": "new",
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


@app.post("/twilio/voice")
async def twilio_voice(request: Request):
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/twilio/speech" method="POST" timeout="5" speechTimeout="auto" language="en-US">
        <Say voice="alice" language="en-US">
            Thank you for calling Westview Dental. I am the virtual receptionist.
            Please briefly tell me what you need help with today.
        </Say>
    </Gather>

    <Say voice="alice" language="en-US">
        I did not hear anything. Please call again.
    </Say>
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
    <Gather input="speech" action="/twilio/collect-name?appointment_id={appointment_id}" method="POST" timeout="6" speechTimeout="auto" language="en-US">
        <Say voice="alice" language="en-US">
            Thank you. I can help create an appointment request.
            May I have your full name?
        </Say>
    </Gather>

    <Say voice="alice" language="en-US">
        I did not hear your name. The front desk will still follow up with you.
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


@app.post("/twilio/collect-name")
async def collect_name(request: Request):
    form = await request.form()
    appointment_id = request.query_params.get("appointment_id")
    patient_name = form.get("SpeechResult", "")

    if appointment_id:
        update_appointment_request(
            appointment_id=appointment_id,
            updates={"patient_name": patient_name},
        )

    safe_name = xml_escape(patient_name)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/twilio/collect-time?appointment_id={appointment_id}" method="POST" timeout="6" speechTimeout="auto" language="en-US">
        <Say voice="alice" language="en-US">
            Thank you, {safe_name}. What day or time would you prefer for this appointment?
        </Say>
    </Gather>

    <Say voice="alice" language="en-US">
        I did not hear a preferred time. The front desk will contact you to confirm.
    </Say>
</Response>
"""
    return Response(content=twiml, media_type="application/xml")


@app.post("/twilio/collect-time")
async def collect_time(request: Request):
    form = await request.form()
    appointment_id = request.query_params.get("appointment_id")
    preferred_time = form.get("SpeechResult", "")

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