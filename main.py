from fastapi import FastAPI, Request
from fastapi.responses import Response

app = FastAPI()


@app.get("/")
def health_check():
    return {"status": "ok", "service": "dental-ai-receptionist"}


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
    caller = form.get("From", "unknown")

    text = speech_result.lower()

    if any(word in text for word in ["appointment", "book", "schedule", "cleaning"]):
        message = f"""
        Thank you. I heard that you need help with an appointment.
        In the next version, I will collect your name, phone number, reason for visit, and preferred time.
        For now, I captured your request as: {speech_result}
        """
    elif any(word in text for word in ["hour", "hours", "open", "location", "address"]):
        message = f"""
        Westview Dental is open Monday to Friday from 9 AM to 5 PM.
        The clinic is located in Vancouver, British Columbia.
        I captured your question as: {speech_result}
        """
    elif any(word in text for word in ["pain", "swelling", "bleeding", "emergency", "urgent", "broken tooth"]):
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
    <Pause length="1"/>
    <Say voice="alice" language="en-US">
        This call came from {caller}. Speech confidence was {confidence}.
    </Say>
</Response>
"""
    return Response(content=twiml, media_type="application/xml")