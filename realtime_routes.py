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
    save_call_to_db,
    update_call,
    match_service_from_transcript,
    save_call_extraction,
    get_active_doctors_for_clinic,
    match_doctor_from_name,
    get_booking_options_for_ai,
    create_appointment_request,
    update_appointment_request,
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

    patient_options = []

    for patient in patient_candidates or []:
        patient_id = patient.get("id")
        full_name = patient.get("full_name")
        phone_primary = patient.get("phone_primary")
        phone_secondary = patient.get("phone_secondary")

        if patient_id and full_name:
            patient_options.append(
                {
                    "id": patient_id,
                    "full_name": full_name,
                    "phone_primary": phone_primary,
                    "phone_secondary": phone_secondary,
                }
            )

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
                        "If the transcript shows the caller clearly confirmed one suggested patient, "
                        "or clearly selected one patient from the provided patient candidates, set patient_id to that exact candidate id "
                        "and patient_identity_confirmed to true. "
                        "If the caller rejected the suggested patient, said it is for someone else, or provided a new name that is not one of the candidates, "
                        "set patient_id to null and patient_identity_confirmed to false, but extract patient_name if clearly provided. "
                        "If multiple patient candidates were offered and the caller selected one by name, set patient_id to that candidate's id. "
                        "Never invent a patient_id. Use only ids from the provided candidates. "
                        "If the caller says a doctor name approximately, phonetically, partially, or in another language, "
                        "match it to the closest available doctor from the provided doctor list. "
                        "If the caller clearly says no preference, set preferred_doctor_name to 'no preference'. "
                        "If the caller did not clearly choose a doctor and did not say no preference, set preferred_doctor_name to null. "
                        "For date and time confirmation, mark date_confirmed or time_confirmed true if the assistant repeated that value "
                        "and the caller clearly agreed directly after that confirmation question. "
                        "Also mark them true if the assistant offered specific appointment slots and the caller clearly selected one of those slots. "
                        "Answers like yes, yeah, correct, درست, بله, آره, ja, oui count as confirmation. "
                        "Answers like no, nope, نه, いや count as rejection. "
                        "If the caller rejected a repeated date or time, do not save the rejected value. "
                        "If the caller corrected a value and then confirmed it, save the corrected value. "
                        "If the caller selected the first or second offered slot, extract that slot's date and time from the assistant's offered options. "
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

            base_realtime_instructions = (
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
                "Only ask for the patient's full name when no existing patient was found for the caller phone number, "
                "or when the caller says the request is for someone else, or when the patient identity is not clear. "
                "Use brief natural acknowledgements only when they help the call feel normal, such as: Sure, I can repeat that. "
                "Do not overuse filler or long status messages. "
                "If the caller asks to repeat, rephrase, say that again, or asks what you just said, repeat the last meaningful assistant message or the last offered options. "
                "Do not treat repeat, rephrase, say that again, what did you say, or can you repeat as a date, time, doctor, reason, yes, no, or slot choice. "
                "After repeating or rephrasing, ask the same pending question again. "
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
                "If the caller says no, no matter the language, the date is rejected and not confirmed. "
                "If the caller says no and provides a corrected date, discard the old date, repeat only the corrected date, and ask if it is correct. "
                "If the caller says no without a clear correction, discard the old date and ask for the preferred date again. "
                "If no preferred date is given, search for the earliest available slots. "
                "Do not ask for a preferred time before using the booking tool. "
                "The preferred time should normally come from one of the suggested appointment slots. "
                "After the tool returns slot suggestions, offer exactly two suggestions when two are available. "
                "Each suggestion must include doctor name, date, and the appointment start time only. "
                "Do not say the appointment end time to the caller. "
                "Keep AM or PM when saying times, because 11 AM and 11 PM are different. "
                "Ask which one works better. "
                "After slot suggestions are given, classify the caller's next answer as one of: select_suggested_slot, change_doctor, change_date, change_doctor_and_date, reject_without_alternative, ask_question, unclear. "
                "If the caller selects one of the suggested slots, accept the selection and say the request has been noted and the front desk will contact them to confirm. "
                "Only treat the caller as selecting a suggested slot if they clearly say the time, the first one, the second one, the earlier one, the later one, that one, or clearly repeat one of the offered options. "
                "Do not infer slot selection from unrelated words, names, greetings, foreign-language fragments, background speech, or unclear audio. "
                "If the answer after slot suggestions is unclear, ask: Did you prefer the first option or the second option? "
                "Do not say the request has been noted until the caller clearly chooses one suggested slot or clearly asks for front desk follow-up. "
                "Never say the appointment is confirmed. "
                "If the caller says a different doctor after suggestions, call get_booking_options again with the updated doctor and the same reason and date if available. "
                "If the caller says a different date after suggestions, confirm that date first, then call get_booking_options again with the updated date. "
                "If the caller says both a different doctor and a different date, update both, confirm the date, then call get_booking_options again. "
                "If the caller rejects the suggested slots without giving a new doctor or date, ask what date they prefer. "
                "If the caller still does not choose a slot, say the front desk will contact them to find another time. "
                "If the booking tool says the requested doctor does not provide the treatment, tell the caller that briefly and offer to check another eligible doctor. "
                "If the booking tool says no slots were found, tell the caller the front desk will contact them to find another time. "
                "If the booking tool says the service was not matched, ask the caller to briefly repeat the reason for the dental visit. "
                "If the caller's answer is garbled, mixed-language, unrelated, or low-confidence, do not convert it into a name, date, time, doctor, reason, or slot choice. "
                "Ask the same field again in the last clearly established language. "
                "Never turn unclear audio into a likely date such as next Tuesday, next Monday, April 22, April 15, or a likely time such as 3 PM or 9:30 AM. "
                "Random words, foreign-language fragments, unrelated words, or unclear sounds are not confirmation. "
                "Only clear yes/no answers in the caller's language count as confirmation. "
                "Do not say the request has been noted until the caller has selected one of the suggested appointment slots, or until the caller agrees that the front desk should follow up. "
                "For severe swelling, uncontrolled bleeding, facial trauma, or trouble breathing, advise emergency medical care immediately."
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
                                    "If the caller still does not choose a slot, say the front desk will contact them to find another time. "
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
                                    "If the caller still does not choose a slot, say the front desk will contact them to find another time. "
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
                                    "If the caller says yes, continue without asking for the name and ask for the reason for the dental visit. "
                                    "If the caller says no or says it is for someone else, ask for the patient's full name. "
                                    "Do not say or expose the patient id to the caller. "
                                )

                            elif len(current_patient_candidates) > 1:
                                patient_names = [
                                    patient.get("full_name")
                                    for patient in current_patient_candidates
                                    if patient.get("full_name")
                                ]

                                patient_context = (
                                    " IMPORTANT PATIENT CONTEXT: "
                                    "The caller phone number matches multiple existing patients. "
                                    f"Patient options: {', '.join(patient_names)}. "
                                    "At the start of the call, after greeting, ask which patient this is for and list the names. "
                                    "If the caller chooses one of the listed patients, continue without asking for the name and ask for the reason for the dental visit. "
                                    "If the caller says it is for someone else, ask for the patient's full name. "
                                    "Do not say or expose any patient id to the caller. "
                                )

                            else:
                                patient_context = (
                                    " IMPORTANT PATIENT CONTEXT: "
                                    "No existing patient was found for this caller phone number. "
                                    "At the start of the call, after greeting, ask for the patient's full name. "
                                )
                            clinic_context = (
                                " IMPORTANT CLINIC NAME CONTEXT: "
                                f"The clinic name is {current_clinic_name}. "
                                "Use this clinic name when greeting the caller. "
                            )

                            session_update = {
                                "type": "session.update",
                                "session": {
                                    "type": "realtime",
                                    "model": OPENAI_REALTIME_MODEL,
                                    "instructions": base_realtime_instructions + clinic_context + doctor_context + patient_context,
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
                                                    "preferred_date_confirmed": {
                                                        "type": "boolean",
                                                        "description": "True only after the assistant repeated the date and the caller confirmed it.",
                                                    },
                                                },
                                                "required": [
                                                    "doctor_name",
                                                    "reason",
                                                    "preferred_date_raw",
                                                    "preferred_date_confirmed",
                                                ],
                                                "additionalProperties": False,
                                            },
                                        }
                                    ],
                                    "tool_choice": "auto",
                                },
                            }

                            await openai_ws.send(json.dumps(session_update))
                            print("Sent OpenAI session.update with clinic, patient context and booking tool")
                            realtime_session_ready = True

                            if len(current_patient_candidates) == 1:
                                patient_name = current_patient_candidates[0].get("full_name") or "this patient"

                                initial_response_instructions = (
                                    "Say exactly and only this sentence, with no extra words: "
                                    f"Hello, thanks for calling {current_clinic_name}. Are you calling for {patient_name}?"
                                )

                            elif len(current_patient_candidates) > 1:
                                patient_names = [
                                    patient.get("full_name")
                                    for patient in current_patient_candidates
                                    if patient.get("full_name")
                                ]

                                names_text = ", ".join(patient_names)

                                initial_response_instructions = (
                                    "Say exactly and only this sentence, with no extra words: "
                                    f"Hello, thanks for calling Westview Dental. Which patient is this for: {names_text}?"
                                )

                            else:
                                initial_response_instructions = (
                                    "Say exactly and only this sentence, with no extra words: "
                                    "Hello, thanks for calling Westview Dental. What is the patient's full name?"
                                )

                            await openai_ws.send(
                                json.dumps(
                                    {
                                        "type": "response.create",
                                        "response": {
                                            "instructions": initial_response_instructions
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

                                should_create_request = bool(
                                    patient_name
                                    or patient_id
                                    or preferred_doctor_name
                                    or reason
                                    or preferred_date_raw
                                    or preferred_time_raw
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

                                tool_result = get_booking_options_for_ai(
                                    clinic_id=current_clinic_id,
                                    doctors=current_doctors,
                                    doctor_name=args.get("doctor_name"),
                                    reason=args.get("reason"),
                                    preferred_date_raw=args.get("preferred_date_raw"),
                                    preferred_date_confirmed=bool(
                                        args.get("preferred_date_confirmed")
                                    ),
                                )

                                print(f"Realtime tool result: {tool_result}")

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

                                await openai_ws.send(
                                    json.dumps({"type": "response.create"})
                                )

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