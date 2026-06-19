from fastapi import FastAPI, Request
from fastapi.responses import Response

app = FastAPI()


@app.get("/")
def health_check():
    return {"status": "ok", "service": "dental-ai-receptionist"}


@app.post("/twilio/voice")
async def twilio_voice(request: Request):
    # Twilio will POST call data here.
    form = await request.form()
    caller = form.get("From", "unknown")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="en-US">
        Thank you for calling Westview Dental. I am the virtual receptionist.
        I can help with appointments, office hours, and urgent dental concerns.
    </Say>
    <Pause length="1"/>
    <Say voice="alice" language="en-US">
        I see you are calling from {caller}. This is a test of our AI receptionist backend.
    </Say>
</Response>
"""
    return Response(content=twiml, media_type="application/xml")