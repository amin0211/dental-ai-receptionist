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
    <Gather input="dtmf" numDigits="1" action="/twilio/menu" method="POST" timeout="6">
        <Say voice="alice" language="en-US">
            Thank you for calling Westview Dental. I am the virtual receptionist.
            Press 1 to request an appointment.
            Press 2 for office hours and location.
            Press 3 if this is an urgent dental concern.
        </Say>
    </Gather>

    <Say voice="alice" language="en-US">
        I did not receive a selection. Please call again.
    </Say>
</Response>
"""
    return Response(content=twiml, media_type="application/xml")


@app.post("/twilio/menu")
async def twilio_menu(request: Request):
    form = await request.form()
    digit = form.get("Digits")

    if digit == "1":
        message = """
        Great. I can help with an appointment request.
        In the next version, I will collect your name, phone number, reason for visit, and preferred time.
        For now, this is a test of the appointment request flow.
        """
    elif digit == "2":
        message = """
        Westview Dental is open Monday to Friday from 9 AM to 5 PM.
        The clinic is located in Vancouver, British Columbia.
        This is a test of the office hours and location flow.
        """
    elif digit == "3":
        message = """
        I am sorry you are dealing with an urgent dental concern.
        If you are experiencing severe swelling, uncontrolled bleeding, facial trauma, or trouble breathing,
        please seek emergency medical care immediately.
        I will mark this as an urgent call for the clinic team.
        """
    else:
        message = """
        Sorry, I did not understand that selection.
        Please call again and choose 1, 2, or 3.
        """

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="en-US">
        {message}
    </Say>
</Response>
"""
    return Response(content=twiml, media_type="application/xml")