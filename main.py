import os
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
@app.get("/")
def health_check():
    return {
        "status": "ok",
        "service": "dental-ai-receptionist",
        "supabase_connected": supabase is not None,
        "has_supabase_url": bool(SUPABASE_URL),
        "has_service_role_key": bool(SUPABASE_SERVICE_ROLE_KEY),
        "supabase_url_preview": SUPABASE_URL[:30] if SUPABASE_URL else None,
    }


def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    return phone.strip()


def detect_intent_and_urgency(text: str) -> tuple[str, str]:
    lower_text = text.lower()

    if any(word in lower_text for word in ["pain", "swelling", "bleeding", "emergency", "urgent", "broken tooth"]):
        return "urgent", "urgent"

    if any(word in lower_text for word in ["appointment", "book", "schedule", "cleaning"]):
        return "appointment", "normal"

    if any(word in lower_text for word in ["hour", "hours", "open", "location", "address"]):
        return "hours_location", "normal"

    return "general", "normal"


def find_clinic_by_twilio_number(to_number: str):
    if not supabase:
        return None

    result = (
        supabase.table("clinics")
        .select("*")
        .eq("phone_number", to_number)
        .limit(1)
        .execute()
    )

    if result.data:
        return result.data[0]

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
        return None

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

    result = supabase.table("calls").insert(payload).execute()

    if result.data:
        return result.data[0]

    return None


def create_appointment_request_if_needed(
    clinic_id: str | None,
    call_id: str | None,
    patient_phone: str | None,
    speech_result: str,
    intent: str,
    urgency: str,
):
    if not supabase:
        return None

    if intent != "appointment":
        return None

    payload = {
        "clinic_id": clinic_id,
        "call_id": call_id,
        "patient_phone": patient_phone,
        "reason": speech_result,
        "urgency": urgency,
        "status": "new",
    }

    result = supabase.table("appointment_requests").insert(payload).execute()

    if result.data:
        return result.data[0]

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

    appointment_request = create_appointment_request_if_needed(
        clinic_id=clinic_id,
        call_id=call_id,
        patient_phone=caller,
        speech_result=speech_result,
        intent=intent,
        urgency=urgency,
    )

    if intent == "appointment":
        if appointment_request:
            message = f"""
            Thank you. I heard that you need help with an appointment.
            I captured your request and will send it to the front desk for follow up.
            Your request was: {speech_result}
            """
        else:
            message = f"""
            Thank you. I heard that you need help with an appointment.
            I captured your request as: {speech_result}
            """
    elif intent == "hours_location":
        message = f"""
        Westview Dental is open Monday to Friday from 9 AM to 5 PM.
        The clinic is located in Vancouver, British Columbia.
        I captured your question as: {speech_result}
        """
    elif intent == "urgent":
        message = f"""
        I am sorry you are dealing with that.
        I heard that this may be an urgent dental concern.
        If you are experiencing severe swelling, uncontrolled bleeding, facial trauma, or trouble breathing,
        please seek emergency medical care immediately.
        I captured your concern as: {speech_result}
        """
    else:
        message = f"""
        Thank you. I captured your message as: {speech_result}.
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