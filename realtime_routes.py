import json
import asyncio

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
) -> dict:
    if not openai_client:
        return {
            "patient_id": None,
            "patient_identity_confirmed": False,
            "patient_name": None,
            "preferred_doctor_name": None,
            "doctor_confirmed": False,
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

                        "PATIENT IDENTITY RULES: "
                        "Use only the provided existing patient candidates. Never invent a patient_id. "
                        "If exactly one patient candidate was suggested and the caller clearly gave an affirmative answer in the caller's language, "
                        "set patient_id to that candidate id and patient_identity_confirmed to true. "
                        "If exactly two patient candidates exist and the assistant asked whether the call is for the first patient, "
                        "then a clear yes confirms the first candidate. A clear no means the second candidate should be used and confirmed, "
                        "unless the caller clearly says it is for someone else. "
                        "If three or more patient candidates exist, the assistant should ask for birth year. "
                        "If the caller gives a birth year and exactly one provided candidate has that birth_year or date_of_birth year, "
                        "set patient_id to that candidate id and patient_identity_confirmed to true. "
                        "If the birth year matches none or multiple candidates, do not choose a patient_id. "
                        "If the caller selects a patient by name, handle accent, phonetic, and transliteration variations, "
                        "Handle cross-language transliteration and phonetic variants, such as Persian or other-language pronunciations of English names. "
                        "Only match names against the provided candidates, not the full database. "
                        "If the caller rejected the suggested patient, said it is for someone else, or provided a new name that is not one of the candidates, "
                        "set patient_id to null and patient_identity_confirmed to false, but extract patient_name if clearly provided. "

                        "If the caller says a doctor name approximately, phonetically, partially, or in another language, "
                        "match it to the closest available doctor from the provided doctor list. "
                        "If the caller clearly says no preference, set preferred_doctor_name to 'no preference'. "
                        "If the caller did not clearly choose a doctor and did not say no preference, set preferred_doctor_name to null. "
                        "For date and time confirmation, mark date_confirmed or time_confirmed true if the assistant repeated that value "
                        "and the caller clearly agreed directly after that confirmation question. "
                        "Also mark them true if the assistant offered specific appointment slots and the caller clearly selected one of those slots. "
                        "Clear affirmative answers in the caller's language count as confirmation. "                        
                        "Clear negative answers in the caller's language count as rejection. "
                        "If the caller rejected a repeated date or time, do not save the rejected value. "
                        "If the caller corrected a value and then confirmed it, save the corrected value. "
                        "If the caller selected the first or second offered slot, extract that slot's date and time from the assistant's offered options. "
                        "CRITICAL SLOT SELECTION RULE: "
                        "After appointment options are offered, do not treat unclear, garbled, foreign-looking, unrelated, or low-confidence caller audio as a slot selection. "
                        "Examples of unclear non-selections include random fragments like Энефорстивäгу, background speech, unknown words, or mixed-language noise. "
                        "The caller selects a slot only if they clearly say first, second, the earlier one, the later one, that one, a specific offered time such as 9 AM or 10 AM, a specific offered date/time, or clearly repeat one of the offered options. "
                        "If the caller response after slot options is unclear, set preferred_date_raw and preferred_time_raw to null, date_confirmed=false, time_confirmed=false, and explain in notes that no slot was clearly selected. "
                        "If a value is unclear, garbled, mixed-language, or uncertain, set it to null and explain in notes. "
                        "For reason, explicit yes/no confirmation is not required if the caller's reason was understandable."
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

        return json.loads(response.output_text)

    except Exception as e:
        return {
            "patient_id": None,
            "patient_identity_confirmed": False,
            "patient_name": None,
            "preferred_doctor_name": None,
            "doctor_confirmed": False,
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
                "Be extremely brief. "
                "Maximum 12 words for normal answers. "
                "Maximum 20 words for appointment slot options. "
                "Do not explain. "
                "Do not add extra context. "
                "Do not say okay, sure, absolutely, thank you, let me check, or I found for you unless necessary. "
                "Ask only one direct question. "
                "For appointment slots, use exactly this style: "
                "'Two options: [date] at [time], or [date] at [time]. Which works?' "
                "For FAQ answers, answer in one short sentence only. "
                "For working hours, answer with only the day and hours. "
                "For appointment lookup, say only date and start time. "
                "For cancellation success, say only: 'Your appointment is cancelled.' "
                "For reschedule success, say only: 'Your request is noted. The front desk will confirm.' "
                "Do not mention doctor names in new appointment slot suggestions. "
                "Do not mention appointment end times. "
                "Never say the appointment is confirmed. "
            )

            voice_cost_control_instructions = (
                "VOICE COST CONTROL: "
                "All spoken replies must be very short. "
                "Default to one short sentence. "
                "Maximum 12 words unless giving two appointment options. "
                "Do not explain your process. "
                "Do not summarize unless asked. "
                "Do not repeat known information unless asked. "
                "Do not use filler acknowledgements. "
                "When asking a question, ask only the question. "
                "When offering appointment slots, say only the date and start time. "
                "Do not say doctor names for new appointment slot suggestions. "
                "Do not say appointment end times. "
                "If a longer answer seems useful, still keep it under one sentence. "
            )

# تو AI receptionist دندانپزشکی هستی
# مودب و حرفه‌ای باش
# اول تماس greeting بده
# زبان caller را تشخیص بده
# اگر فارسی صحبت کرد فارسی جواب بده
# اگر صدا نامفهوم بود حدس نزن
# یک سوال در هر بار بپرس
            core_realtime_instructions = (
                "You are a concise, warm, and professional AI receptionist for the dental clinic. "
                "Start the call naturally by greeting the caller, then follow the IMPORTANT PATIENT CONTEXT exactly. "
                "Start in neutral English unless the caller clearly speaks another language first. "
                "Reply in the caller's clearly detected language. "
                "If the caller clearly speaks Persian/Farsi at any point, switch to Persian/Farsi and continue in Persian/Farsi. "
                "If the caller clearly asks to use another language, switch to that language. "
                "If the caller's speech is mixed, garbled, or unclear, do not switch languages based on that unclear fragment. "
                "When speech is unclear, stay in the last clearly established language and ask the caller to repeat clearly. "
                "Do not switch languages because of one random foreign-looking transcript fragment. "
                "Keep replies short, natural, and receptionist-like. "
                "Normally ask exactly one question at a time. "
                "Do not ask for more than one new field in the same reply. "
            )

# سوالات عمومی کلینیک 
            faq_realtime_instructions = (
                "FAQ HANDLING: "
                "The caller may ask general clinic questions that are not appointment booking requests. "
                "Examples include: Do you accept insurance, do you offer direct billing, do you have parking, "
                "do you accept children, do you offer emergency appointments, do you do wisdom tooth removal, "
                "what services do you provide, what is your cancellation policy, or similar clinic policy questions. "
                "When the caller asks a general clinic question, call the get_faq_answer tool with the caller's exact question. "
                "If get_faq_answer returns ok=true and faq.answer exists, answer using only that FAQ answer. "
                "Keep the answer short, natural, and receptionist-like. "
                "Do not invent clinic policies, prices, insurance coverage, treatment guarantees, parking details, or availability details. "
                "If the FAQ answer says something depends on insurance plan, availability, provider, patient condition, or dentist assessment, "
                "tell the caller the front desk can verify it. "
                "If get_faq_answer returns ok=false, say you are not fully sure about that specific question and offer to have the front desk follow up. "
                "Do not answer clinic FAQ questions from general knowledge. Always use clinic-specific FAQ data when available. "
                "If the FAQ question turns into booking, for example the caller asks about wisdom tooth and then wants an appointment, "
                "answer the FAQ first, then continue the normal booking flow by asking for the dental visit reason or using the stated reason. "
                "For emergency-related FAQ, do not diagnose and do not promise treatment. "
                "If the caller mentions severe swelling, trouble breathing, uncontrolled bleeding, fever, facial trauma, or serious injury, "
                "advise them to call 911 or go to the nearest emergency room, and if collecting appointment information mark the request as urgent. "
            )

# ساعت کاری 
            working_hours_realtime_instructions = (
                "WORKING HOURS HANDLING: "
                "If the caller asks about clinic hours, opening hours, closing time, whether the clinic is open, "
                "or a specific doctor's working hours, call the get_working_hours tool. "
                "Examples include: What are your hours, are you open today, what time do you close, "
                "is Dr. Smith working on Monday, clinic hours, doctor hours, opening hours, closing hours. "
                "Use get_working_hours instead of get_faq_answer for working-hours questions. "
                "If the caller asks about a specific doctor, pass the doctor name. "
                "If the caller mentions a specific day or date, pass it as date_raw. "
                "If the caller asks general hours without a date, pass date_raw as null. "
                "Answer only using the tool result. Do not invent hours. "
                "If the tool says no hours were found, say the front desk can verify the hours. "
                "Do not treat a working-hours question as an appointment booking request unless the caller clearly says they want to book, schedule, change, or cancel an appointment. "
            )

# repeat please
# وقتی صدا نامفهوم
            repeat_and_clarity_instructions = (
                "Only ask for the patient's full name when no existing patient was found for the caller phone number, "
                "or when the caller says the request is for someone else, or when the patient identity is not clear. "
                "Use brief natural acknowledgements only when they help the call feel normal, such as: Sure, I can repeat that. "
                "Do not overuse filler or long status messages. "
                "If the caller asks to repeat, rephrase, say that again, or asks what you just said, repeat the last meaningful assistant message or the last offered options. "
                "Do not treat repeat, rephrase, say that again, what did you say, or can you repeat as a date, time, doctor, reason, yes, no, appointment lookup, cancellation, reschedule, or slot choice. "
                "After repeating or rephrasing, ask the same pending question again. "
            )

# وقت‌های موجود بیمار 
            appointment_lookup_instructions = (
                "If the caller asks about an existing appointment, appointment time, appointment reminder, upcoming appointment, "
                "or says phrases like when is my appointment, what time is my appointment, remind me of my appointment, or the equivalent in the caller's language, do not call get_booking_options. "
                "First make sure the patient identity is clear and confirmed. "
                "If one existing patient matches the phone number, ask if the call is for that patient. If yes, use that patient's id. "
                "If multiple patients match the phone number, follow the patient identity flow from IMPORTANT PATIENT CONTEXT. "
                "For two patients, confirm the first patient; if the caller says no, use the second patient and say that patient's name clearly. "
                "For three or more patients, ask for the patient's year of birth and match it only against the phone-number patient candidates. "
                "After the caller selects or confirms one patient, use that patient's id. "

                "If no existing patient is found or the patient is not confirmed, ask for the patient's full name and say the front desk can help verify the appointment. "
                "Only call get_upcoming_appointments when you have a confirmed existing patient_id. "
                "When appointment lookup returns appointments, tell the caller the earliest upcoming appointment with doctor name, date, and start time only. "
                "If multiple upcoming appointments are returned and the caller asks generally about their appointment time, tell the earliest one first. "
                "Do not create a new appointment request when the caller only asks to check or remind an existing appointment. "
                "If no upcoming appointment is found, say you cannot find an upcoming appointment and the front desk can help. "
            )

#  برای cancel کردن وقت
            cancellation_instructions = (
                "If the caller asks to cancel an existing appointment, do not call get_booking_options. "
                "First confirm the patient identity. Then call get_upcoming_appointments for the confirmed patient. "
                "If exactly one upcoming appointment is available, repeat that appointment with doctor name, date, and start time, then ask for final yes/no confirmation before cancelling. "
                "If multiple upcoming appointments are available, list them as first, second, third with doctor name, date, and start time, then ask which one they want to cancel. "
                "After the caller chooses an appointment to cancel, repeat the exact appointment and ask for final yes/no confirmation. "
                "Only call cancel_appointment after the caller clearly confirms yes to cancelling that exact appointment. "
                "Never cancel an appointment based on unclear audio, background speech, maybe, or ambiguous yes. "
                "After cancel_appointment succeeds, tell the caller the appointment has been cancelled. "
                "If cancel_appointment fails, tell the caller the front desk can help cancel it. "
            )

# می‌خوام وقتمو عوض کنم
            reschedule_instructions = (
                "If the caller asks to change, move, modify, or reschedule an existing appointment, do not call get_booking_options first. "
                "First confirm the patient identity. Then call get_upcoming_appointments for the confirmed patient. "
                "If exactly one upcoming appointment is available, repeat that appointment with doctor name, date, and start time, then ask what date they prefer instead. "
                "If multiple upcoming appointments are available, list them as first, second, third with doctor name, date, and start time, then ask which appointment they want to change. "
                "After the caller chooses which appointment to change, ask what date they prefer instead. "
                "When the caller gives a new date for rescheduling, repeat only that date and ask if it is correct. "
                "After the new date is confirmed, call get_booking_options using the original appointment reason or service if available, the original doctor if available, and the confirmed new date. "
                "Offer exactly two new slot suggestions when available. "
                "After the caller clearly selects one new slot, call reschedule_appointment with the original appointment id, confirmed patient id, selected slot doctor_id, starts_at, and ends_at. "
                "Only reschedule after the caller clearly selects one new offered slot. "
                "Never reschedule based on unclear audio, background speech, maybe, or ambiguous yes. "
                "After reschedule_appointment succeeds, tell the caller the previous appointment has been cancelled and the new appointment request has been noted. "
                "Never say the new appointment is confirmed. "
                "Say the front desk will contact them to confirm. "
                "If reschedule_appointment fails, tell the caller the front desk can help reschedule it. "
            )

# اول patient identity
# بعد reason
# اگر reason واضح بود get_booking_options
# اگر تاریخ داد، تاریخ را confirm کن
# بعد دو slot پیشنهاد بده
# اسم دکتر نگو
# end time نگو
# فقط date و start time بگو
            booking_instructions = (
                "For appointment booking, do not force the caller to choose a doctor first. "
                "If the caller already mentions a doctor, remember that doctor preference. "
                "If the caller does not mention a doctor, ask the reason for the dental visit after patient identity has been handled. "
                "For reason, ask only why they want the dental visit. "
                "If the reason is specific enough to map to a dental service or symptom, accept it. "
                "If the caller only says a vague reason such as problem, issue, something is wrong, I need a dentist, or I have a concern, ask one follow-up question to clarify the dental problem before calling get_booking_options. "
                "Examples of specific enough reasons: tooth pain, cleaning, checkup, broken tooth, filling, crown, wisdom tooth, bleeding gums, swelling, emergency, or orthodontic concern. "
                "Do not call get_booking_options when the only reason is vague. "
                "Do not ask for confirmation of the reason unless it is unclear. "
                "If the reason is unclear, ask why they want the dental visit again. "
                "After the dental reason is clear, use the get_booking_options tool to find appointment options. "
                "The booking tool uses the treatment duration, eligible doctors, recurring doctor availability, and calendar events from the clinic database. "
                "If the caller already mentioned a doctor, include that doctor name in the tool call. "
                "If the caller did not mention a doctor, pass doctor_name as null. "
                "If the caller gives a preferred date, repeat only the understood date and ask if it is correct before using that date for slot search. "
                "Never introduce a date that was not clearly spoken by the caller or returned by the booking tool. "
                "Never ask whether a random date is correct. "
                "If the caller asks for repetition after slot options, repeat the same slot options exactly; do not ask for date confirmation. "
                "If no date is currently pending confirmation, do not ask 'Is [date] correct?'. "
                "Only confirm a date immediately after the caller clearly gave that date. "
                "The date is not collected until the caller clearly confirms it after you repeat it. "
                "When asking a yes/no confirmation question, the caller's answer must clearly mean yes or no in the established conversation language. "
                "If the answer is not clearly yes and not clearly no, do not advance the flow. "
                "Say that you did not understand, then repeat the same yes/no question. "
                "Do not treat unrelated words, names, foreign-language fragments, background speech, or unclear audio as yes or no. "

                "If the caller says no, no matter the language, the date is rejected and not confirmed. "
                "If the caller says no and provides a corrected date, discard the old date, repeat only the corrected date, and ask if it is correct. "
                "If the caller says no without a clear correction, discard the old date and ask for the preferred date again. "
                "If no preferred date is given, search for the earliest available slots. "

                "Do not ask for a preferred time before using the booking tool, but if the caller gives a time preference, keep it. "
                "If the caller says a time preference such as morning, afternoon, evening, after 2 PM, before noon, or a specific time, keep that as preferred_time_raw. "
                "If the caller gives a time range such as between 2 and 4, from 3 to 5, or the equivalent in the caller's language, keep the full range as preferred_time_raw. "
                "If the caller says both a different date and time preference, confirm both together, for example: 'Tomorrow afternoon, correct?' "
                "After the caller confirms the date and time preference, call get_booking_options with preferred_date_raw and preferred_time_raw. "
                "Never ignore morning, afternoon, evening, after, before, between, from-to, or specific time preferences. "
                "If the caller requested afternoon, do not offer morning slots. "

                "The preferred time should normally come from one of the suggested appointment slots. "
                "Even if the selected slot contains doctor_name internally, never include doctor_name in the spoken slot suggestion. "
                "If the caller requested a specific doctor, search only that doctor internally, but still offer only the date and time to the caller. "
                "If the caller did not request a specific doctor, search eligible doctors internally, but still offer only the date and time to the caller. "
                "Do not say the appointment end time to the caller. "
                "Keep the doctor_id internally from the selected slot, but do not mention the doctor's name to the caller. "
                "Keep AM or PM when saying times, because 11 AM and 11 PM are different. "
                "Ask which one works better. "
                "After slot suggestions are given, classify the caller's next answer as one of: select_suggested_slot, change_doctor, change_date, change_doctor_and_date, reject_without_alternative, ask_question, unclear. "
                "If the caller selects one of the suggested slots, accept the selection and say the request has been noted and the front desk will contact them to confirm. "
                "Only treat the caller as selecting a suggested slot if they clearly say the time, the first one, the second one, the earlier one, the later one, that one, or clearly repeat one of the offered options. "
                "Do not infer slot selection from unrelated words, names, greetings, foreign-language fragments, background speech, or unclear audio. "
                "If the answer after slot suggestions is unclear, garbled, unrelated, foreign-looking, or low-confidence, do not treat it as slot selection. "
                "Ask exactly: Did you prefer the first option or the second option? "
                "Never say the request has been noted after unclear audio. "
                "Never say the front desk will confirm until the caller clearly chooses the first option, second option, or repeats one offered date/time. "
                "Do not say the request has been noted until the caller clearly chooses one suggested slot or clearly asks for front desk follow-up. "
                "Never say the appointment is confirmed. "
                "When re-offering slots after a doctor change, do not mention the doctor's name in the slot suggestions. "
                "If the caller says a different date after suggestions, confirm that date first, then call get_booking_options again with the updated date. "
                "If the caller says both a different doctor and a different date, update both, confirm the date, then call get_booking_options again. "
                "If the caller rejects the suggested slots without giving a new doctor or date, ask what date they prefer. "
                "If the caller still does not choose a slot after you ask one follow-up question, say the front desk will contact them to find another time. "
                "If the booking tool says the requested doctor does not provide the treatment, tell the caller that briefly and offer to check another eligible doctor. "
                "If the booking tool says no slots were found, tell the caller the front desk will contact them to find another time. "
                "If the booking tool says the service was not matched, ask the caller to briefly repeat the reason for the dental visit. "
            )

# اگر caller چیزی گفت که واضح نبود، حدس نزن.
# از روی صدای خراب تاریخ یا ساعت نساز.
# اگر severe swelling، trouble breathing، uncontrolled bleeding، facial trauma گفت،
# به emergency room یا 911 راهنمایی کن.؟
            unclear_audio_and_safety_instructions = (
                "If the caller's answer is garbled, mixed-language, unrelated, or low-confidence, do not convert it into a name, date, time, doctor, reason, appointment id, cancellation, reschedule, or slot choice. "
                "Ask the same field again in the last clearly established language. "
                "Never turn unclear audio into a likely date such as next Tuesday, next Monday, April 22, April 15, or a likely time such as 3 PM or 9:30 AM. "
                "Random words, foreign-language fragments, unrelated words, or unclear sounds are not confirmation. "
                "Only clear yes/no answers in the established conversation language count as confirmation or rejection. "
                "If the pending question expects yes/no and the caller's answer is not clearly yes or no, repeat the same question instead of advancing. "

                "Do not say the request has been noted until the caller has selected one of the suggested appointment slots, or until the caller agrees that the front desk should follow up. "
                "For severe swelling, uncontrolled bleeding, facial trauma, or trouble breathing, advise emergency medical care immediately. "
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
                                    "Do not force the caller to choose a doctor first. "
                                    "If the caller mentions a doctor at any point, treat it as preferred_doctor_name and use that doctor for booking search. "
                                    "If the caller does not mention a doctor, ask the reason for the dental visit after patient identity has been handled. "
                                    "After the reason is clear, call the get_booking_options tool. "
                                    "If no doctor was requested, the tool will find eligible doctors for that treatment. "
                                    "If a doctor was requested, the tool will check that doctor and treatment combination. "
                                    "If the caller gives a preferred date, confirm the date before calling the tool with that date. "
                                    "After slot suggestions are given, if the caller says a different doctor or different date, call the tool again with the updated preference. "
                                    "If the caller selects one of the suggested slots, accept the selection and say the request has been noted and the front desk will contact them to confirm. "
                                    "If the caller rejects the suggested slots without a new doctor or date, ask what date they prefer. "
                                    "If the caller still does not choose a slot after you ask one follow-up question, say the front desk will contact them to find another time. "
                                    "Ask only one direct question at a time. "
                                    "Only ask for the patient's full name when no existing patient was found for the caller phone number, "
                                    "or when the caller says the request is for someone else, or when the patient identity is not clear. "
                                )
                            else:
                                doctor_context = (
                                    " IMPORTANT CLINIC CONTEXT: "
                                    "This clinic has zero or one active doctor. "
                                    "Do not ask which doctor the caller prefers. "
                                    "Ask the reason for the dental visit after patient identity has been handled. "
                                    "After the reason is clear, call the get_booking_options tool to suggest appointment slots. "
                                    "If the caller gives a preferred date, confirm the date before calling the tool with that date. "
                                    "After slot suggestions are given, if the caller says a different date, call the tool again with the updated date. "
                                    "If the caller selects one of the suggested slots, accept the selection and say the request has been noted and the front desk will contact them to confirm. "
                                    "If the caller rejects the suggested slots without a new date, ask what date they prefer. "
                                    "If the caller still does not choose a slot after you ask one follow-up question, say the front desk will contact them to find another time. "
                                    "Ask only one direct question at a time. "
                                    "Only ask for the patient's full name when no existing patient was found for the caller phone number, "
                                    "or when the caller says the request is for someone else, or when the patient identity is not clear. "
                                )

                            if len(current_patient_candidates) == 1:
                                patient = current_patient_candidates[0]
                                patient_context = (
                                    " IMPORTANT PATIENT CONTEXT: "
                                    "The caller phone number matches one existing patient. "
                                    f"Patient option: id={patient.get('id')}, name={patient.get('full_name')}. "
                                    f"At the start of the call, after greeting, ask: Are you calling for {patient.get('full_name')}? "

                                    "This is a yes/no identity confirmation question. "
                                    "If the caller clearly gives an affirmative answer in the established conversation language, treat this patient as confirmed. "
                                    "If the caller repeats the suggested patient's name and it clearly refers to this patient, treat it as confirmation. "
                                    "If the caller clearly gives a negative answer, says a different name, or says the request is for someone else, ask for the patient's full name. "
                                    "If the caller's answer is not clearly yes and not clearly no, do not continue to booking. "
                                    "Say that you did not understand, then repeat the same identity confirmation question. "
                                    "Do not ask for the dental visit reason until the patient identity is confirmed. "

                                    "If the caller asks about an existing appointment, call get_upcoming_appointments with this patient's id. "
                                    "If the caller asks to cancel an appointment, call get_upcoming_appointments with this patient's id first. "
                                    "If the caller asks to change or reschedule an appointment, call get_upcoming_appointments with this patient's id first. "
                                    "If the caller says no or says it is for someone else, ask for the patient's full name. "
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
                                    f"At the start of the call, after greeting, ask exactly: Are you calling for {first_name}? "
                                    f"If the caller clearly says yes, use {first_name}'s patient id and treat identity as confirmed. "
                                    f"If the caller clearly says no, use {second_name}'s patient id and say clearly that you will use {second_name}'s profile. "
                                    "Do not ask the caller to say the second patient's name after they already said no to the first patient. "
                                    "If the caller says it is for someone else, ask for the patient's full name. "
                                    "If the caller asks about an existing appointment after identity is confirmed, call get_upcoming_appointments with the confirmed patient id. "
                                    "If the caller asks to cancel an appointment after identity is confirmed, call get_upcoming_appointments with the confirmed patient id first. "
                                    "If the caller asks to change or reschedule an appointment after identity is confirmed, call get_upcoming_appointments with the confirmed patient id first. "
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
                                    "At the start of the call, after greeting, do not read all patient names. "
                                    "Ask for the patient's year of birth. "
                                    "Match the birth year only against the provided patient candidates from this phone number. "
                                    "If exactly one candidate matches the birth year, use that patient's id, treat identity as confirmed, "
                                    "and say the patient's name clearly. "
                                    "If no candidate or more than one candidate matches the birth year, ask for the patient's first name or full name. "
                                    "When matching a spoken name, handle accent, phonetic, and transliteration variations, "
                                    "Handle cross-language transliteration and phonetic variants of candidate names. "
                                    "Only match against the provided candidates, not the full database. "
                                    "If the caller says it is for someone else, ask for the patient's full name. "
                                    "If the caller asks about an existing appointment after identity is confirmed, call get_upcoming_appointments with the confirmed patient id. "
                                    "If the caller asks to cancel an appointment after identity is confirmed, call get_upcoming_appointments with the confirmed patient id first. "
                                    "If the caller asks to change or reschedule an appointment after identity is confirmed, call get_upcoming_appointments with the confirmed patient id first. "
                                    "Do not say or expose any patient id to the caller. "
                                )
                            else:
                                patient_context = (
                                    " IMPORTANT PATIENT CONTEXT: "
                                    "No existing patient was found for this caller phone number. "
                                    "At the start of the call, after greeting, ask for the patient's full name. "
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
                                                "whether the clinic is open on a specific date or day, or a specific doctor's working hours. "
                                                "This tool reads calendar_availability_rules and calendar_availability_exceptions. "
                                                "Clinic-level rules use doctor_id = null. Doctor-specific rules use that doctor's id."
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

                            if len(current_patient_candidates) == 1:
                                patient_name = get_patient_display_name(
                                    current_patient_candidates[0]
                                )
                                
                                initial_response_instructions = (
                                    "Say exactly and only this sentence, with no extra words: "
                                    f"Hello, thanks for calling {current_clinic_name}. Are you calling for {patient_name}?"
                                )

                            elif len(current_patient_candidates) == 2:
                                first_patient_name = get_patient_display_name(
                                    current_patient_candidates[0]
                                )

                                initial_response_instructions = (
                                    "Say exactly and only this sentence, with no extra words: "
                                    f"Hello, thanks for calling {current_clinic_name}. Are you calling for {first_patient_name}?"
                                )

                            elif len(current_patient_candidates) >= 3:
                                initial_response_instructions = (
                                    "Say exactly and only this sentence, with no extra words: "
                                    f"Hello, thanks for calling {current_clinic_name}. What is the patient's year of birth?"
                                )

                            else:
                                initial_response_instructions = (
                                    "Say exactly and only this sentence, with no extra words: "
                                    f"Hello, thanks for calling {current_clinic_name}. What is the patient's full name?"
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
                                )

                                preferred_doctor_name = appointment_details.get("preferred_doctor_name")

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

                                should_create_request = (
                                    appointment_request_write_needed
                                    and not is_non_booking_management_call
                                    and slot_was_selected
                                    and bool(reason)
                                )

                                if should_create_request:
                                    appointment_request = create_appointment_request(
                                        clinic_id=current_clinic_id,
                                        call_id=current_call_id,
                                        patient_phone=current_caller_phone,
                                        patient_id=patient_id,
                                        patient_name=patient_name,
                                        reason=reason,
                                        preferred_time=preferred_time_combined,
                                        urgency=urgency,
                                        status="new",
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
                                        f"patient_id={patient_id}, service={service_match}, details={appointment_details}"
                                    )

                                else:
                                    print(
                                        "No appointment request created after-call AI extraction. "
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

                                print(f"Realtime booking tool result: {tool_result}")

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

                                # Important:
                                # Working-hours questions are informational only.
                                # Do NOT set appointment_request_write_needed = True here.

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

                                # Appointment lookup is informational.
                                # Do NOT set appointment_request_write_needed = True here.

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

                                # Cancel updates the appointment directly.
                                # Do NOT set appointment_request_write_needed = True here.

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

                                # Very important:
                                # Reschedule uses get_booking_options before this, which sets
                                # appointment_request_write_needed = True.
                                # But reschedule_appointment_for_ai already cancels the old appointment
                                # and creates the new appointment_request.
                                # Therefore, reset this flag to avoid creating a duplicate request at call end.
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