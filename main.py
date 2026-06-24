import os
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import Response
from supabase import create_client, Client

from config import PUBLIC_WS_URL
from realtime_routes import router as realtime_router

from supabase_service import (
    normalize_phone,
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