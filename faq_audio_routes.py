import hashlib
import os
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from supabase_service import supabase


router = APIRouter()

FAQ_AUDIO_BUCKET = "faq-audio"
FAQ_TTS_MODEL = "gpt-4o-mini-tts"
FAQ_TTS_VOICE = "alloy"


class RegenerateFaqAudioBody(BaseModel):
    clinic_id: str


def make_faq_audio_hash(answer: str, voice: str = FAQ_TTS_VOICE) -> str:
    clean_answer = answer.strip()
    raw = f"{voice}|{clean_answer}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_openai_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    return OpenAI(api_key=api_key)


@router.post("/admin/faqs/{faq_id}/regenerate-audio")
async def regenerate_faq_audio(faq_id: str, body: RegenerateFaqAudioBody):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client is not initialized.")

    try:
        faq_res = (
            supabase.table("clinic_faqs")
            .select("*")
            .eq("id", faq_id)
            .eq("clinic_id", body.clinic_id)
            .single()
            .execute()
        )

        faq = faq_res.data

        if not faq:
            raise HTTPException(status_code=404, detail="FAQ not found.")

        answer = (faq.get("answer") or "").strip()

        if not answer:
            raise HTTPException(status_code=400, detail="FAQ answer is empty.")

        audio_hash = make_faq_audio_hash(answer)

        if (
            faq.get("audio_hash") == audio_hash
            and faq.get("audio_status") == "ready"
            and faq.get("audio_url")
        ):
            return {
                "ok": True,
                "skipped": True,
                "faq_id": faq_id,
                "audio_url": faq.get("audio_url"),
            }

        now = datetime.now(timezone.utc).isoformat()

        supabase.table("clinic_faqs").update(
            {
                "audio_status": "generating",
                "audio_error": None,
                "updated_at": now,
            }
        ).eq("id", faq_id).eq("clinic_id", body.clinic_id).execute()

        openai_client = get_openai_client()

        speech = openai_client.audio.speech.create(
            model=FAQ_TTS_MODEL,
            voice=FAQ_TTS_VOICE,
            input=answer,
            response_format="mp3",
        )

        audio_bytes = speech.read()

        storage_path = f"clinics/{body.clinic_id}/faqs/{faq_id}/{audio_hash}.mp3"

        tmp_path = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                supabase.storage.from_(FAQ_AUDIO_BUCKET).upload(
                    path=storage_path,
                    file=tmp_path,
                    file_options={
                        "content-type": "audio/mpeg",
                        "upsert": "true",
                    },
                )
            except Exception as upload_error:
                error_text = str(upload_error)

                # اگر فایل از قبل وجود داشت، چون اسم فایل بر اساس hash است،
                # همان فایل قبلی قابل استفاده است.
                if "already exists" not in error_text.lower() and "duplicate" not in error_text.lower():
                    raise upload_error

        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        public_url = supabase.storage.from_(FAQ_AUDIO_BUCKET).get_public_url(storage_path)

        finished_at = datetime.now(timezone.utc).isoformat()

        supabase.table("clinic_faqs").update(
            {
                "audio_url": public_url,
                "audio_storage_path": storage_path,
                "audio_hash": audio_hash,
                "audio_status": "ready",
                "audio_error": None,
                "audio_generated_at": finished_at,
                "updated_at": finished_at,
            }
        ).eq("id", faq_id).eq("clinic_id", body.clinic_id).execute()

        return {
            "ok": True,
            "skipped": False,
            "faq_id": faq_id,
            "audio_url": public_url,
            "audio_storage_path": storage_path,
        }

    except HTTPException:
        raise

    except Exception as error:
        error_message = str(error)

        try:
            supabase.table("clinic_faqs").update(
                {
                    "audio_status": "failed",
                    "audio_error": error_message,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", faq_id).eq("clinic_id", body.clinic_id).execute()
        except Exception:
            pass

        raise HTTPException(status_code=500, detail=error_message)