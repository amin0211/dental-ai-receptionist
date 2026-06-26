import json
import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from openai import AsyncOpenAI
import websockets

from config import (
    OPENAI_API_KEY,
    OPENAI_REALTIME_MODEL,
    OPENAI_EXTRACTION_MODEL,
)
from openai_usage_tracker import (
    create_openai_usage_totals,
    track_realtime_response_done,
    persist_call_openai_usage,
    print_usage_summary,
)

from supabase_service import (
    normalize_phone,
    find_clinic_by_twilio_number,
    find_patients_by_phone,
    build_patient_options_for_ai,
    get_patient_display_name,
    get_patient_birth_year,
    save_call_to_db,
    update_call,
    match_service_from_transcript,
    save_call_extraction,
    get_active_doctors_for_clinic,
    match_doctor_from_name,
    get_booking_options_for_ai,
    create_appointment_request,
    update_appointment_request,
    get_upcoming_appointments_for_ai,
    cancel_appointment_for_ai,
    reschedule_appointment_for_ai,
    get_faq_answer_for_ai,
    get_working_hours_for_ai,
)

router = APIRouter()

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


async def extract_appointment_details_with_openai(
    transcript: str,
    doctors: list[dict] | None = None,
    patient_candidates: list[dict] | None = None,
    booking_options_history: list[dict] | None = None,
) -> dict:
    if not openai_client:
        return {
            "patient_id": None,
            "patient_identity_confirmed": False,
            "patient_name": None,
            "preferred_doctor_name": None,
            "doctor_confirmed": False,
            "selected_slot_doctor_id": None,
            "selected_slot_doctor_name": None,
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

    doctor_list_text = (
        ", ".join(doctor_names) if doctor_names else "No doctor list provided."
    )

    patient_options = build_patient_options_for_ai(patient_candidates or [])

    patient_list_text = (
        json.dumps(patient_options, ensure_ascii=False)
        if patient_options
        else "No existing patients were found for the caller phone number."
    )

    booking_options_text = (
        json.dumps(booking_options_history or [], ensure_ascii=False)
        if booking_options_history
        else "No booking options were offered."
    )

    schema = {
        "type": "object",
        "properties": {
            "patient_id": {
                "type": ["string", "null"],
                "description": (
                    "Existing patient UUID only if the caller clearly confirmed "
                    "or selected one of the provided existing patient candidates. "
                    "Never invent an id."
                ),
            },
            "patient_identity_confirmed": {
                "type": "boolean",
                "description": (
                    "True only if the caller clearly confirmed the suggested patient "
                    "or clearly selected one of the listed existing patients."
                ),
            },
            "patient_name": {
                "type": ["string", "null"],
                "description": (
                    "Patient full name only if clearly provided, clearly confirmed, "
                    "or available from a confirmed existing patient candidate."
                ),
            },
            "preferred_doctor_name": {
                "type": ["string", "null"],
                "description": (
                    "The preferred doctor name if the caller clearly chose one, "
                    "or 'no preference' if the caller clearly said they have no preference."
                ),
            },
            "doctor_confirmed": {
                "type": "boolean",
                "description": (
                    "True if the caller clearly selected a doctor or clearly said they have no preference. "
                    "Explicit yes/no confirmation is not required."
                ),
            },
            "selected_slot_doctor_id": {
                "type": ["string", "null"],
                "description": (
                    "Doctor id from the selected offered appointment slot. "
                    "Use only doctor_id values from the provided booking_options_history. "
                    "Set null if no offered slot was clearly selected."
                ),
            },
            "selected_slot_doctor_name": {
                "type": ["string", "null"],
                "description": (
                    "Doctor name from the selected offered appointment slot. "
                    "Use only doctor_name values from the provided booking_options_history. "
                    "Set null if no offered slot was clearly selected."
                ),
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
                "description": (
                    "Preferred appointment time or selected suggested slot time only if clearly provided or selected."
                ),
            },
            "name_confirmed": {
                "type": "boolean",
                "description": (
                    "True if the patient name was clearly confirmed, or if an existing patient candidate was confirmed."
                ),
            },
            "date_confirmed": {
                "type": "boolean",
                "description": (
                    "True only if the assistant repeated the date and the caller clearly confirmed it, "
                    "or the caller selected a suggested slot with a specific date."
                ),
            },
            "time_confirmed": {
                "type": "boolean",
                "description": (
                    "True only if the assistant repeated the time and the caller clearly confirmed it, "
                    "or the caller selected a suggested slot with a specific time."
                ),
            },
            "reason_confirmed": {
                "type": "boolean",
                "description": (
                    "True if the reason was clearly stated. Explicit yes/no confirmation is not required for reason."
                ),
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
                "description": (
                    "Short explanation of missing, rejected, unclear, selected, or uncertain values."
                ),
            },
        },
        "required": [
            "patient_id",
            "patient_identity_confirmed",
            "patient_name",
            "preferred_doctor_name",
            "doctor_confirmed",
            "selected_slot_doctor_id",
            "selected_slot_doctor_name",
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

    try:
        extraction_started_at = time.perf_counter()

        response = await openai_client.responses.create(
            model=OPENAI_EXTRACTION_MODEL,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Extract structured appointment details from this phone call transcript. "
                        "Use only information supported by the transcript. "
                        "Do not guess or invent patient names, patient ids, doctor names, dates, times, or reasons. "
                        f"The available doctors for this clinic are: {doctor_list_text}. "
                        f"Existing patient candidates for the caller phone are: {patient_list_text}. "
                        f"Booking options offered during the call are: {booking_options_text}. "

                        "PATIENT IDENTITY RULES: "
                        "Use only the provided existing patient candidates. Never invent a patient_id. "
                        "If exactly one patient candidate was suggested and the caller clearly gave an affirmative answer, "
                        "set patient_id to that candidate id and patient_identity_confirmed to true. "
                        "If exactly two patient candidates exist and the assistant asked whether the call is for the first patient, "
                        "then a clear yes confirms the first candidate. A clear no means the second candidate should be used and confirmed, "
                        "unless the caller clearly says it is for someone else. "
                        "If three or more patient candidates exist, use birth year only if it matches exactly one provided candidate. "
                        "If the caller selects a patient by name, match only against provided candidates, including phonetic or transliteration variants. "
                        "If the caller rejected the suggested patient, said it is for someone else, or provided a new name not in candidates, "
                        "set patient_id to null and patient_identity_confirmed to false, but extract patient_name if clearly provided. "

                        "DOCTOR RULES: "
                        "If the caller says a doctor name approximately, phonetically, partially, or in another language, "
                        "match it to the closest available doctor from the provided doctor list. "
                        "If the caller clearly says no preference, set preferred_doctor_name to 'no preference'. "
                        "If no doctor was clearly chosen, set preferred_doctor_name to null. "

                        "DATE AND TIME RULES: "
                        "Mark date_confirmed or time_confirmed true only if the assistant repeated that value and the caller clearly agreed, "
                        "or if the caller clearly selected a specific offered slot. "
                        "Clear affirmative answers in the caller's language count as confirmation. "
                        "Clear negative answers count as rejection. "
                        "If the caller rejected a repeated date or time, do not save the rejected value. "
                        "If the caller corrected a value and then confirmed it, save the corrected value. "

                        "OFFERED SLOT RULES: "
                        "If the caller clearly selected the first or second offered slot, extract that slot's date and time from the offered options. "
                        "Also extract selected_slot_doctor_id and selected_slot_doctor_name from booking_options_history. "
                        "Use slot order exactly as offered: first means slots[0], second means slots[1]. "
                        "If caller selected by repeating an offered date/time, match it to the corresponding offered slot. "
                        "Never infer doctor_id from transcript. Use only booking_options_history. "

                        "CRITICAL SLOT SELECTION RULE: "
                        "After appointment options are offered, do not treat unclear, garbled, foreign-looking, unrelated, or low-confidence caller audio as a slot selection. "
                        "Invalid examples include Tekanwa, Førstebarn, Kjozde, ん, えー, Hallo, hello, yes, okay, mm-hmm, background speech, random fragments, or mixed-language noise. "
                        "The caller selects a slot only if they clearly say first, first one, option one, second, second one, option two, earlier one, later one, "
                        "a specific offered time, a specific offered date/time, or clearly repeat one of the offered options. "
                        "If the caller response after slot options is unclear, set preferred_date_raw and preferred_time_raw to null, "
                        "date_confirmed=false, time_confirmed=false, selected_slot_doctor_id=null, selected_slot_doctor_name=null, "
                        "and explain in notes that no slot was clearly selected. "

                        "If a value is unclear, garbled, mixed-language, or uncertain, set it to null and explain in notes. "
                        "For reason, explicit yes/no confirmation is not required if the caller's reason was understandable. "
                        "If the caller wanted an appointment but some fields are missing or unclear, still extract any supported fields and explain missing fields in notes. "
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

        extraction_duration = time.perf_counter() - extraction_started_at
        print(
            "Appointment extraction completed | "
            f"duration_seconds={extraction_duration:.3f}"
        )

        return json.loads(response.output_text)

    except Exception as e:
        print(f"Appointment extraction failed: {e}")

        return {
            "patient_id": None,
            "patient_identity_confirmed": False,
            "patient_name": None,
            "preferred_doctor_name": None,
            "doctor_confirmed": False,
            "selected_slot_doctor_id": None,
            "selected_slot_doctor_name": None,
            "reason": None,
            "preferred_date_raw": None,
            "preferred_time_raw": None,
            "name_confirmed": False,
            "date_confirmed": False,
            "time_confirmed": False,
            "reason_confirmed": False,
            "language": "unknown",
            "confidence": 0.0,
            "notes": f"Failed to extract appointment details: {e}",
        }


@router.websocket("/twilio/realtime")
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

    openai_usage_totals = create_openai_usage_totals()

    current_clinic_id = None
    current_clinic_name = "the dental clinic"
    current_caller_phone = None
    current_doctors = []
    current_patient_candidates = []
    booking_options_history = []

    appointment_request_write_needed = False
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

            short_audio_response_instructions = (
                "Reply in the caller's current language. "
                "Be brief and natural. "
                "Ask only one question at a time. "
                "Do not explain your process. "
                "Do not say okay, sure, thank you, one moment, let me check, or I will check before using a tool. "
                "When a tool is needed, call the tool silently first, then answer with the result. "

                "CONFIRMATION RULE: "
                "Valid yes examples: yes, yeah, correct, right, that's right, sure, بله, آره, درسته. "
                "Valid no examples: no, nope, incorrect, not correct, نه, خیر, درست نیست. "
                "If the caller's answer is unclear, ambiguous, garbled, unrelated, foreign-looking, or not in the valid yes/no list, do not treat it as confirmation or rejection. "
                "Do not move to the next step. "
                "Ask the exact same confirmation question one more time. "
                "For appointment slots, always say exactly: "
                "'Two options: [date] at [time], or [date] at [time]. Which works?' "
                "Use only each slot's display field when speaking appointment options. "
                "Do not speak starts_at, date, start_time, or the year unless the display field includes it. "
                "Never shorten the second option to only the time. "
                "Do not mention doctor names or end times in new appointment slot suggestions. "
                "Never say an appointment is confirmed. "
                "For FAQ answers, use one short sentence. "
                "For working hours, answer with only the day and hours. "
                "For cancellation success, say only: 'Your appointment is cancelled.' "
                "For reschedule success, say only: 'Your request is noted. The front desk will confirm.' "
            )

            voice_cost_control_instructions = (
                "VOICE RULES: "
                "Keep spoken replies short. "
                "Default to one short sentence. "
                "Do not summarize unless asked. "
                "Do not repeat known information unless needed. "
                "Do not use filler acknowledgements. "
                "When asking a question, ask only that question. "
                "When using tools, do not speak a status sentence first. "
                "Call the tool silently, then answer with the result only. "
            )

            core_realtime_instructions = (
                "You are a concise, warm, professional AI receptionist for the dental clinic. "
                "Start by greeting the caller and asking how you can help. "
                "Do not ask for patient identity at the start of the call. "
                "Ask for patient identity only when the caller wants to book, check, cancel, or reschedule an appointment. "
                "Start in English unless the caller clearly speaks another language first. "
                "Reply in the caller's clearly detected language. "
                "If the caller clearly speaks Persian/Farsi, switch to Persian/Farsi. "
                "Do not switch languages because of unclear, random, or foreign-looking transcript fragments. "
                "If speech is unclear, stay in the last clear language and ask the same pending question again. "
                "Ask one question at a time. "
                "Never confirm an appointment as booked. "
            )

            faq_realtime_instructions = (
                "FAQ HANDLING: "
                "For general clinic questions such as insurance, direct billing, parking, children, services, emergency availability, wisdom teeth, cancellation policy, or payment policy, call get_faq_answer. "
                "Answer only from the FAQ tool result. "
                "Do not invent clinic policies, prices, coverage, parking, availability, or treatment guarantees. "
                "If FAQ lookup fails, say the front desk can follow up. "
                "If the caller then wants to book, continue booking flow. "
                "For severe swelling, trouble breathing, uncontrolled bleeding, fever, facial trauma, or serious injury, advise emergency care or 911. "
            )

            working_hours_realtime_instructions = (
                "WORKING HOURS HANDLING: "
                "For clinic hours, opening hours, closing time, open today/tomorrow, or doctor working hours, call get_working_hours. "
                "Use get_working_hours instead of FAQ for hours questions. "
                "Pass doctor_name only if a specific doctor is mentioned. "
                "Pass date_raw only if a day or date is mentioned. "
                "Answer only using the tool result. "
                "Do not treat hours questions as booking unless the caller clearly asks to book, schedule, change, cancel, or check an appointment. "
            )

            repeat_and_clarity_instructions = (
                "CLARITY AND REPEAT RULES: "
                "Only ask for patient identity for appointment-related requests. "
                "Only ask for full name if no existing patient was found, the caller says it is for someone else, or identity is unclear during an appointment-related request. "
                "If the caller asks to repeat, rephrase, or says what did you say, repeat the last meaningful question or slot options. "
                "Do not treat repeat requests as date, time, doctor, reason, yes, no, cancellation, reschedule, or slot choice. "
                "After repeating, ask the same pending question again. "
            )

            appointment_lookup_instructions = (
                "APPOINTMENT LOOKUP: "
                "If the caller asks about an existing appointment, appointment time, reminder, or upcoming appointment, do not call get_booking_options. "
                "First confirm patient identity using IMPORTANT PATIENT CONTEXT. "
                "Only call get_upcoming_appointments after you have a confirmed existing patient_id. "
                "If appointments are found, tell the earliest appointment with doctor name, date, and start time only. "
                "If none are found, say you could not find an upcoming appointment and the front desk can help. "
                "Do not create a new appointment request for lookup-only calls. "
            )

            cancellation_instructions = (
                "CANCELLATION: "
                "If the caller wants to cancel an existing appointment, do not call get_booking_options. "
                "First confirm patient identity, then call get_upcoming_appointments. "
                "If one appointment exists, repeat doctor name, date, and start time, then ask for final yes/no confirmation. "
                "If multiple appointments exist, list them as first, second, third, then ask which one. "
                "Only call cancel_appointment after the caller clearly confirms cancelling that exact appointment. "
                "Never cancel based on unclear audio, background speech, maybe, or ambiguous yes. "
            )

            reschedule_instructions = (
                "RESCHEDULE: "
                "If the caller wants to change, move, or reschedule an existing appointment, do not call get_booking_options first. "
                "First confirm patient identity, then call get_upcoming_appointments. "
                "If one appointment exists, repeat doctor name, date, and start time, then ask what date they prefer. "
                "If multiple appointments exist, list them as first, second, third, then ask which appointment to change. "
                "After the caller gives a new date, repeat the date and ask if correct. "
                "After date confirmation, call get_booking_options using the original reason/service and original doctor if available. "
                "Offer two new slots. "
                "Only call reschedule_appointment after the caller clearly selects one offered new slot. "
                "Never say the new appointment is confirmed. "
            )

            booking_instructions = (
                "BOOKING FLOW: "
                "For new appointment booking, first confirm patient identity using IMPORTANT PATIENT CONTEXT. "
                "Do not force the caller to choose a doctor. "
                "If the caller mentions a doctor, keep it as doctor_name. "
                "After identity is handled, ask for the dental visit reason. "

                "REASON RULES: "
                "Accept specific reasons such as tooth pain, cleaning, checkup, broken tooth, filling, crown, wisdom tooth, bleeding gums, swelling, emergency, or orthodontic concern. "
                "If the reason is vague, such as problem, issue, concern, or I need a dentist, ask one follow-up question to clarify. "
                "Do not call get_booking_options for a vague reason only. "
                "Do not ask to confirm the reason unless unclear. "

                "DATE AND TIME RULES: "
                "If the caller gives a preferred date, repeat only that date and ask if correct before using it. "
                "Only use a preferred date after the caller clearly confirms it. "
                "If the caller says no, discard the date and ask for the preferred date again unless they give a corrected date. "
                "If the caller gives a time preference such as morning, afternoon, evening, after 2 PM, before noon, or a range, keep it as preferred_time_raw. "
                "If the caller confirms a date plus time preference, call get_booking_options with both. "
                "If no date is given, call get_booking_options for earliest available slots. "
                "If the caller changes only time preference after a date was already confirmed, keep the same date and call get_booking_options with the new time preference. "

                "TOOL RULES: "
                "Call get_booking_options silently. Do not say let me check or I will check before the tool. "
                "Pass doctor_name if requested, otherwise null. "
                "Pass preferred_date_confirmed true only after the caller confirmed the date. "
                "Use returned slots only. Do not invent dates or times. "

                "SLOT OFFER RULES: "
                "Offer exactly two slots when available. "
                "Say exactly: Two options: [slot 1 display], or [slot 2 display]. Which works? "
                "Use only each slot's display field when speaking appointment options. "
                "Do not speak starts_at, date, start_time, or the year unless the display field includes it. "
                "Do not mention doctor names or end times. "

                "SLOT SELECTION AND CONFIRMATION RULES: "
                "When asking any confirmation question, continue only after a clear valid answer. "
                "If the caller gives an unclear, ambiguous, garbled, unrelated, or invalid answer, do not advance the flow and repeat the same confirmation question once. "
                "For slot selection, valid answers are only: first, first one, option one, second, second one, option two, earlier one, later one, or an exact offered time. "
                "Invalid examples: Tekanwa, Tekkenman, Førstebarn, Kjozde, ん, えー, Hallo, hello, yes after a which-option question, okay after a which-option question, background speech. "
                "If the answer after slot options is not a valid slot choice, ask exactly once: Did you prefer the first option or the second option? "
                "If still unclear after that, say: The front desk will contact you to find the best time. "
                "Never say the request is noted until a clear slot choice is made. "
                "Never say the appointment is confirmed. "

                "FOLLOW-UP RULES: "
                "If no slots are found, say the front desk will contact them to find another time. "
                "If the requested doctor does not provide the treatment, say that briefly and offer another eligible doctor. "
                "If service is not matched, ask the caller to repeat the dental reason briefly. "
                "Handle only one new appointment request per call. "
                "If the caller asks for multiple appointments, handle the first and say the front desk will help with the others. "
            )

            unclear_audio_and_safety_instructions = (
                "UNCLEAR AUDIO SAFETY: "
                "Do not convert garbled, mixed-language, unrelated, or low-confidence speech into a name, date, time, doctor, reason, appointment id, cancellation, reschedule, or slot choice. "
                "Ask the same pending question again in the last clear language. "
                "Do not turn unclear audio into likely dates or times. "
                "Only clear yes/no answers count for yes/no questions. "
                "For slot selection, unclear audio is not first or second. "
                "If slot selection is unclear, ask once: Did you prefer the first option or the second option? "
                "For severe swelling, uncontrolled bleeding, facial trauma, or trouble breathing, advise emergency medical care immediately. "
                "CONFIRMATION SAFETY: "
                "If the pending question expects yes/no and the caller's answer is not in the valid yes/no set, do not advance. "
                "Repeat the same yes/no question once. "
                "If the pending question expects first/second slot choice and the caller's answer is not a valid slot choice, do not advance. "
                "Ask exactly once: Did you prefer the first option or the second option? "
                "Never map unclear words to yes, no, first, or second. "
            )

            async def create_short_audio_response():
                await openai_ws.send(
                    json.dumps(
                        {
                            "type": "response.create",
                            "response": {
                                "instructions": short_audio_response_instructions,
                            },
                        }
                    )
                )

            async def receive_from_twilio():
                nonlocal stream_sid
                nonlocal current_call_id
                nonlocal current_clinic_id
                nonlocal current_clinic_name
                nonlocal current_caller_phone
                nonlocal transcript_parts
                nonlocal current_doctors
                nonlocal current_patient_candidates
                nonlocal booking_options_history
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
                            clinic_name = clinic.get("name") if clinic else None

                            current_clinic_id = clinic_id
                            current_clinic_name = clinic_name or "the dental clinic"
                            current_caller_phone = caller

                            print(f"Resolved clinic | id={current_clinic_id} name={current_clinic_name}")

                            current_doctors = get_active_doctors_for_clinic(clinic_id)
                            print(f"Active doctors for clinic: {current_doctors}")

                            current_patient_candidates = find_patients_by_phone(
                                clinic_id=clinic_id,
                                phone=caller,
                            )
                            booking_options_history = []

                            print(f"Patient candidates for caller phone: {current_patient_candidates}")

                            if len(current_doctors) > 1:
                                doctor_names = [
                                    doctor.get("display_name") or doctor.get("full_name")
                                    for doctor in current_doctors
                                    if doctor.get("display_name") or doctor.get("full_name")
                                ]

                                doctor_context = (
                                    " IMPORTANT CLINIC CONTEXT: "
                                    f"This clinic has multiple active doctors: {', '.join(doctor_names)}. "
                                    "Do not force the caller to choose a doctor. "
                                    "If the caller mentions a doctor, keep that doctor preference for booking search. "
                                    "If no doctor is mentioned, use eligible doctors internally. "
                                    "Never mention doctor names in new appointment slot suggestions. "
                                )
                            else:
                                doctor_context = (
                                    " IMPORTANT CLINIC CONTEXT: "
                                    "This clinic has zero or one active doctor. "
                                    "Do not ask which doctor the caller prefers. "
                                    "Use the available doctor internally for booking search when possible. "
                                    "Never mention doctor names in new appointment slot suggestions. "
                                )

                            if len(current_patient_candidates) == 1:
                                patient = current_patient_candidates[0]
                                patient_name = get_patient_display_name(patient)

                                patient_context = (
                                    " IMPORTANT PATIENT CONTEXT: "
                                    "The caller phone number matches one existing patient. "
                                    f"Patient option: id={patient.get('id')}, name={patient_name}. "
                                    "Do not ask for patient identity at the start of the call. "
                                    "Only when the caller wants to book, check, cancel, or reschedule an appointment, ask: "
                                    f"Is this for {patient_name}? "
                                    "If the caller clearly says yes, use this patient's id and treat identity as confirmed. "
                                    "If the caller repeats the suggested patient's name and it clearly refers to this patient, treat it as confirmation. "
                                    "If the caller clearly says no, says a different name, or says it is for someone else, ask for the patient's full name. "
                                    "If the caller's answer is unclear, repeat the same identity confirmation question. "
                                    "Do not ask for the dental visit reason until patient identity is confirmed for booking. "
                                    "Do not say or expose the patient id to the caller. "
                                )

                            elif len(current_patient_candidates) == 2:
                                first_patient = current_patient_candidates[0]
                                second_patient = current_patient_candidates[1]

                                first_name = get_patient_display_name(first_patient)
                                second_name = get_patient_display_name(second_patient)

                                patient_options_for_ai = build_patient_options_for_ai(
                                    current_patient_candidates
                                )

                                patient_context = (
                                    " IMPORTANT PATIENT CONTEXT: "
                                    "The caller phone number matches exactly two existing patients. "
                                    f"First patient option: name={first_name}, id={first_patient.get('id')}. "
                                    f"Second patient option: name={second_name}, id={second_patient.get('id')}. "
                                    f"Internal patient candidates for tool use only: {json.dumps(patient_options_for_ai, ensure_ascii=False)}. "
                                    "Do not ask for patient identity at the start of the call. "
                                    "Only when the caller wants to book, check, cancel, or reschedule an appointment, ask exactly: "
                                    f"Is this for {first_name}? "
                                    f"If the caller clearly says yes, use {first_name}'s patient id and treat identity as confirmed. "
                                    f"If the caller clearly says no, use {second_name}'s patient id and say briefly that you will use {second_name}'s profile. "
                                    "Do not ask the caller to say the second patient's name after they already said no to the first patient. "
                                    "If the caller says it is for someone else, ask for the patient's full name. "
                                    "If the caller's answer is unclear, repeat the same identity confirmation question. "
                                    "Do not say or expose any patient id to the caller. "
                                )

                            elif len(current_patient_candidates) >= 3:
                                patient_options_for_ai = build_patient_options_for_ai(
                                    current_patient_candidates
                                )

                                patient_context = (
                                    " IMPORTANT PATIENT CONTEXT: "
                                    "The caller phone number matches three or more existing patients, likely a family phone number. "
                                    f"Internal patient candidates for tool use only: {json.dumps(patient_options_for_ai, ensure_ascii=False)}. "
                                    "Do not ask for patient identity at the start of the call. "
                                    "Only when the caller wants to book, check, cancel, or reschedule an appointment, ask for the patient's year of birth. "
                                    "Do not read all patient names. "
                                    "Match the birth year only against the provided patient candidates from this phone number. "
                                    "If exactly one candidate matches the birth year, use that patient's id, treat identity as confirmed, and say the patient's name clearly. "
                                    "If no candidate or more than one candidate matches the birth year, ask for the patient's first name or full name. "
                                    "When matching a spoken name, handle accent, phonetic, and transliteration variations. "
                                    "Only match against the provided candidates, not the full database. "
                                    "If the caller says it is for someone else, ask for the patient's full name. "
                                    "Do not say or expose any patient id to the caller. "
                                )

                            else:
                                patient_context = (
                                    " IMPORTANT PATIENT CONTEXT: "
                                    "No existing patient was found for this caller phone number. "
                                    "Do not ask for the patient's full name at the start of the call. "
                                    "Only when the caller wants to book, check, cancel, or reschedule an appointment, ask for the patient's full name. "
                                    "For appointment lookup, cancellation, or reschedule requests, explain that the front desk can help verify the appointment if no existing patient can be confirmed. "
                                )

                            clinic_context = (
                                " IMPORTANT CLINIC NAME CONTEXT: "
                                f"The clinic name is {current_clinic_name}. "
                                "Use this clinic name when greeting the caller. "
                            )

                            realtime_instruction_sections = [
                                voice_cost_control_instructions,
                                core_realtime_instructions,
                                faq_realtime_instructions,
                                working_hours_realtime_instructions,
                                repeat_and_clarity_instructions,
                                appointment_lookup_instructions,
                                cancellation_instructions,
                                reschedule_instructions,
                                booking_instructions,
                                unclear_audio_and_safety_instructions,
                                clinic_context,
                                doctor_context,
                                patient_context,
                            ]

                            full_realtime_instructions = "".join(
                                realtime_instruction_sections
                            )

                            session_update = {
                                "type": "session.update",
                                "session": {
                                    "type": "realtime",
                                    "model": OPENAI_REALTIME_MODEL,
                                    "instructions": full_realtime_instructions,
                                    "output_modalities": ["audio"],
                                    "audio": {
                                        "input": {
                                            "format": {"type": "audio/pcmu"},
                                            "transcription": {"model": "gpt-4o-transcribe"},
                                            "turn_detection": {
                                                "type": "server_vad",
                                                "threshold": 0.5,
                                                "prefix_padding_ms": 600,
                                                "silence_duration_ms": 700,
                                            },
                                        },
                                        "output": {
                                            "format": {"type": "audio/pcmu"},
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
                                                    "preferred_time_raw": {
                                                        "type": ["string", "null"],
                                                        "description": (
                                                            "Preferred time or time range if the caller gave one, such as morning, afternoon, "
                                                            "evening, after 2 PM, before noon, 3 PM, between 2 and 4, from 3 to 5, "
                                                            "or equivalent time-preference phrases in the caller's language. "
                                                            "Use null if no time preference."
                                                        ),
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
                                                    "preferred_time_raw",
                                                    "preferred_date_confirmed",
                                                ],
                                                "additionalProperties": False,
                                            },
                                        },
                                        {
                                            "type": "function",
                                            "name": "get_faq_answer",
                                            "description": (
                                                "Use this when the caller asks a general clinic FAQ question, "
                                                "such as insurance, direct billing, parking, children, emergency availability, "
                                                "wisdom teeth, clinic services, cancellation policy, payment policy, or other "
                                                "non-booking clinic questions. This tool returns the clinic-specific answer."
                                            ),
                                            "parameters": {
                                                "type": "object",
                                                "properties": {
                                                    "caller_question": {
                                                        "type": "string",
                                                        "description": "The caller's exact clinic question or statement.",
                                                    },
                                                },
                                                "required": ["caller_question"],
                                                "additionalProperties": False,
                                            },
                                        },
                                        {
                                            "type": "function",
                                            "name": "get_working_hours",
                                            "description": (
                                                "Use this when the caller asks about clinic hours, opening hours, closing time, "
                                                "whether the clinic is open on a specific date or day, or a specific doctor's working hours."
                                            ),
                                            "parameters": {
                                                "type": "object",
                                                "properties": {
                                                    "caller_question": {
                                                        "type": "string",
                                                        "description": "The caller's exact question about hours or working availability.",
                                                    },
                                                    "doctor_name": {
                                                        "type": ["string", "null"],
                                                        "description": "Doctor name if the caller asks about a specific doctor, otherwise null.",
                                                    },
                                                    "date_raw": {
                                                        "type": ["string", "null"],
                                                        "description": "Specific day or date mentioned by the caller, such as today, tomorrow, Monday, July 20, or null for general weekly hours.",
                                                    },
                                                },
                                                "required": [
                                                    "caller_question",
                                                    "doctor_name",
                                                    "date_raw",
                                                ],
                                                "additionalProperties": False,
                                            },
                                        },
                                        {
                                            "type": "function",
                                            "name": "get_upcoming_appointments",
                                            "description": (
                                                "Look up upcoming appointments for a confirmed existing patient. "
                                                "Use this when the caller asks about appointment time, appointment reminder, "
                                                "or when the caller wants to cancel or reschedule an existing appointment."
                                            ),
                                            "parameters": {
                                                "type": "object",
                                                "properties": {
                                                    "patient_id": {
                                                        "type": "string",
                                                        "description": "Confirmed existing patient id.",
                                                    },
                                                },
                                                "required": ["patient_id"],
                                                "additionalProperties": False,
                                            },
                                        },
                                        {
                                            "type": "function",
                                            "name": "cancel_appointment",
                                            "description": (
                                                "Cancel one confirmed upcoming appointment after patient identity is confirmed, "
                                                "the appointment is identified, and the caller gives final clear yes confirmation."
                                            ),
                                            "parameters": {
                                                "type": "object",
                                                "properties": {
                                                    "patient_id": {
                                                        "type": "string",
                                                        "description": "Confirmed existing patient id.",
                                                    },
                                                    "appointment_id": {
                                                        "type": "string",
                                                        "description": "The exact appointment id selected from get_upcoming_appointments.",
                                                    },
                                                },
                                                "required": ["patient_id", "appointment_id"],
                                                "additionalProperties": False,
                                            },
                                        },
                                        {
                                            "type": "function",
                                            "name": "reschedule_appointment",
                                            "description": (
                                                "Reschedule one confirmed upcoming appointment after patient identity is confirmed, "
                                                "the original appointment is identified, and the caller clearly selects a new offered slot."
                                            ),
                                            "parameters": {
                                                "type": "object",
                                                "properties": {
                                                    "patient_id": {
                                                        "type": "string",
                                                        "description": "Confirmed existing patient id.",
                                                    },
                                                    "appointment_id": {
                                                        "type": "string",
                                                        "description": "The exact original appointment id selected from get_upcoming_appointments.",
                                                    },
                                                    "doctor_id": {
                                                        "type": "string",
                                                        "description": "Doctor id from the selected new slot returned by get_booking_options.",
                                                    },
                                                    "start_time_iso": {
                                                        "type": "string",
                                                        "description": "starts_at value from the selected new slot returned by get_booking_options.",
                                                    },
                                                    "end_time_iso": {
                                                        "type": "string",
                                                        "description": "ends_at value from the selected new slot returned by get_booking_options.",
                                                    },
                                                },
                                                "required": [
                                                    "patient_id",
                                                    "appointment_id",
                                                    "doctor_id",
                                                    "start_time_iso",
                                                    "end_time_iso",
                                                ],
                                                "additionalProperties": False,
                                            },
                                        },
                                    ],
                                    "tool_choice": "auto",
                                },
                            }

                            await openai_ws.send(json.dumps(session_update))
                            print("Sent OpenAI session.update with clinic, patient context and tools")
                            realtime_session_ready = True

                            initial_response_instructions = (
                                "Say exactly and only this sentence, with no extra words: "
                                f"Hello, thanks for calling {current_clinic_name}. How can I help?"
                            )

                            await openai_ws.send(
                                json.dumps(
                                    {
                                        "type": "response.create",
                                        "response": {
                                            "instructions": initial_response_instructions,
                                        },
                                    }
                                )
                            )

                            print("Sent initial OpenAI greeting response.create")

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

                                persist_call_openai_usage(
                                    call_id=current_call_id,
                                    totals=openai_usage_totals,
                                    update_call_func=update_call,
                                    model=OPENAI_REALTIME_MODEL,
                                    extra_updates={
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
                                    current_patient_candidates,
                                    booking_options_history,
                                )

                                preferred_doctor_name = appointment_details.get("preferred_doctor_name")

                                selected_slot_doctor_id = appointment_details.get("selected_slot_doctor_id")
                                selected_slot_doctor_name = appointment_details.get("selected_slot_doctor_name")

                                doctor_id = selected_slot_doctor_id or None

                                if selected_slot_doctor_name:
                                    preferred_doctor_name = selected_slot_doctor_name

                                if not doctor_id:
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

                                extracted_reason = appointment_details.get("reason")

                                service_match = None

                                if extracted_reason:
                                    service_match = match_service_from_transcript(
                                        current_clinic_id,
                                        extracted_reason,
                                    )

                                if not service_match:
                                    service_match = match_service_from_transcript(
                                        current_clinic_id,
                                        caller_only_transcript,
                                    )

                                patient_name = appointment_details.get("patient_name")
                                patient_id = appointment_details.get("patient_id")
                                patient_identity_confirmed = bool(
                                    appointment_details.get("patient_identity_confirmed")
                                )

                                valid_patient_ids = {
                                    patient.get("id")
                                    for patient in current_patient_candidates
                                    if patient.get("id")
                                }

                                if not patient_identity_confirmed or patient_id not in valid_patient_ids:
                                    patient_id = None

                                if patient_id:
                                    matched_patient = next(
                                        (
                                            patient
                                            for patient in current_patient_candidates
                                            if patient.get("id") == patient_id
                                        ),
                                        None,
                                    )

                                    if matched_patient:
                                        patient_name = matched_patient.get("full_name") or patient_name

                                reason = (
                                    service_match["canonical_reason"]
                                    if service_match
                                    else extracted_reason
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
                                    patient_id=patient_id,
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

                                non_booking_management_phrases = [
                                    "when is my appointment",
                                    "what time is my appointment",
                                    "remind me of my appointment",
                                    "appointment time",
                                    "upcoming appointment",
                                    "cancel my appointment",
                                    "cancel appointment",
                                    "cancel the appointment",
                                    "reschedule my appointment",
                                    "reschedule appointment",
                                    "change my appointment",
                                    "move my appointment",
                                    "modify my appointment",
                                    "وقت من کیه",
                                    "ساعت وقتم",
                                    "وقت دندان",
                                    "زمان وقتم",
                                    "وقتمو کنسل",
                                    "وقتم رو کنسل",
                                    "کنسل کنم",
                                    "کنسل کردن وقت",
                                    "وقتمو عوض",
                                    "وقتم رو عوض",
                                    "تغییر وقت",
                                    "عوض کردن وقت",
                                    "جابجا کردن وقت",
                                ]

                                transcript_lower = full_transcript.lower()

                                is_non_booking_management_call = any(
                                    phrase.lower() in transcript_lower
                                    for phrase in non_booking_management_phrases
                                )

                                slot_was_selected = bool(
                                    preferred_date_raw
                                    and preferred_time_raw
                                    and date_confirmed
                                    and time_confirmed
                                )

                                request_status = "new" if slot_was_selected else "needs_followup"

                                should_create_request = bool(
                                    appointment_request_write_needed
                                    and not is_non_booking_management_call
                                )

                                print(
                                    "Appointment request decision | "
                                    f"appointment_request_write_needed={appointment_request_write_needed}, "
                                    f"is_non_booking_management_call={is_non_booking_management_call}, "
                                    f"slot_was_selected={slot_was_selected}, "
                                    f"request_status={request_status}, "
                                    f"reason={reason}, "
                                    f"extracted_reason={extracted_reason}, "
                                    f"preferred_date_raw={preferred_date_raw}, "
                                    f"preferred_time_raw={preferred_time_raw}, "
                                    f"date_confirmed={date_confirmed}, "
                                    f"time_confirmed={time_confirmed}, "
                                    f"doctor_id={doctor_id}, "
                                    f"preferred_doctor_name={preferred_doctor_name}, "
                                    f"booking_options_history_count={len(booking_options_history)}, "
                                    f"should_create_request={should_create_request}"
                                )

                                if should_create_request:
                                    appointment_request = create_appointment_request(
                                        clinic_id=current_clinic_id,
                                        call_id=current_call_id,
                                        patient_phone=current_caller_phone,
                                        patient_id=patient_id,
                                        patient_name=patient_name,
                                        reason=reason or extracted_reason or "Appointment request needs follow-up",
                                        preferred_time=preferred_time_combined,
                                        urgency=urgency,
                                        status=request_status,
                                        doctor_id=doctor_id,
                                        preferred_doctor_name=preferred_doctor_name,
                                    )

                                    if appointment_request:
                                        updates = {
                                            "patient_id": patient_id,
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
                                        f"status={request_status}, patient_id={patient_id}, "
                                        f"service={service_match}, details={appointment_details}"
                                    )

                                else:
                                    print(
                                        "No appointment request created after-call AI extraction. "
                                        f"appointment_request_write_needed={appointment_request_write_needed}, "
                                        f"is_non_booking_management_call={is_non_booking_management_call}, "
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
                nonlocal booking_options_history
                nonlocal openai_usage_totals
                nonlocal current_call_id
                nonlocal appointment_request_write_needed

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

                                appointment_request_write_needed = True

                                tool_started_at = time.perf_counter()

                                tool_result = get_booking_options_for_ai(
                                    clinic_id=current_clinic_id,
                                    doctors=current_doctors,
                                    doctor_name=args.get("doctor_name"),
                                    reason=args.get("reason"),
                                    preferred_date_raw=args.get("preferred_date_raw"),
                                    preferred_time_raw=args.get("preferred_time_raw"),
                                    preferred_date_confirmed=bool(
                                        args.get("preferred_date_confirmed")
                                    ),
                                )

                                tool_duration = time.perf_counter() - tool_started_at

                                print(
                                    "Realtime booking tool result | "
                                    f"duration_seconds={tool_duration:.3f} | "
                                    f"args={args} | "
                                    f"result={tool_result}"
                                )

                                if tool_result.get("ok") and tool_result.get("slots"):
                                    booking_options_history.append(
                                        {
                                            "tool_call_index": len(booking_options_history) + 1,
                                            "doctor_name_requested": args.get("doctor_name"),
                                            "reason": args.get("reason"),
                                            "preferred_date_raw": args.get("preferred_date_raw"),
                                            "preferred_time_raw": args.get("preferred_time_raw"),
                                            "preferred_date_confirmed": bool(
                                                args.get("preferred_date_confirmed")
                                            ),
                                            "slots": tool_result.get("slots") or [],
                                        }
                                    )

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

                                await create_short_audio_response()

                            elif tool_name == "get_faq_answer":
                                try:
                                    args = json.loads(arguments_raw)
                                except Exception as e:
                                    print(f"Failed to parse FAQ arguments: {e}")
                                    args = {}

                                tool_result = get_faq_answer_for_ai(
                                    clinic_id=current_clinic_id,
                                    caller_question=args.get("caller_question"),
                                )

                                print(f"Realtime FAQ tool result: {tool_result}")

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

                                await create_short_audio_response()

                            elif tool_name == "get_working_hours":
                                try:
                                    args = json.loads(arguments_raw)
                                except Exception as e:
                                    print(f"Failed to parse working hours arguments: {e}")
                                    args = {}

                                tool_result = get_working_hours_for_ai(
                                    clinic_id=current_clinic_id,
                                    doctors=current_doctors,
                                    caller_question=args.get("caller_question"),
                                    doctor_name=args.get("doctor_name"),
                                    date_raw=args.get("date_raw"),
                                )

                                print(f"Realtime working hours tool result: {tool_result}")

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

                                await create_short_audio_response()

                            elif tool_name == "get_upcoming_appointments":
                                try:
                                    args = json.loads(arguments_raw)
                                except Exception as e:
                                    print(f"Failed to parse appointment lookup arguments: {e}")
                                    args = {}

                                tool_result = get_upcoming_appointments_for_ai(
                                    clinic_id=current_clinic_id,
                                    patient_id=args.get("patient_id"),
                                )

                                print(f"Realtime appointment lookup result: {tool_result}")

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

                                await create_short_audio_response()

                            elif tool_name == "cancel_appointment":
                                try:
                                    args = json.loads(arguments_raw)
                                except Exception as e:
                                    print(f"Failed to parse cancel appointment arguments: {e}")
                                    args = {}

                                tool_result = cancel_appointment_for_ai(
                                    clinic_id=current_clinic_id,
                                    patient_id=args.get("patient_id"),
                                    appointment_id=args.get("appointment_id"),
                                )

                                print(f"Realtime cancel appointment result: {tool_result}")

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

                                await create_short_audio_response()

                            elif tool_name == "reschedule_appointment":
                                try:
                                    args = json.loads(arguments_raw)
                                except Exception as e:
                                    print(f"Failed to parse reschedule appointment arguments: {e}")
                                    args = {}

                                tool_result = reschedule_appointment_for_ai(
                                    clinic_id=current_clinic_id,
                                    patient_id=args.get("patient_id"),
                                    appointment_id=args.get("appointment_id"),
                                    doctor_id=args.get("doctor_id"),
                                    start_time_iso=args.get("start_time_iso"),
                                    end_time_iso=args.get("end_time_iso"),
                                    call_id=current_call_id,
                                    patient_phone=current_caller_phone,
                                )

                                print(f"Realtime reschedule appointment result: {tool_result}")

                                if tool_result.get("ok"):
                                    appointment_request_write_needed = False

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

                                await create_short_audio_response()

                            else:
                                print(f"Unknown realtime tool requested: {tool_name}")

                        elif event_type == "response.done":
                            track_realtime_response_done(openai_usage_totals, response)

                            print_usage_summary(
                                "OpenAI event: response.done",
                                openai_usage_totals,
                            )

                            persist_call_openai_usage(
                                call_id=current_call_id,
                                totals=openai_usage_totals,
                                update_call_func=update_call,
                                model=OPENAI_REALTIME_MODEL,
                            )

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