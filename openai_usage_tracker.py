import os
from typing import Any, Callable


def get_price_per_1m_tokens(env_name: str, default: str = "0") -> float:
    try:
        return float(os.environ.get(env_name, default))
    except Exception:
        return 0.0


OPENAI_TEXT_INPUT_PRICE_PER_1M = get_price_per_1m_tokens(
    "OPENAI_TEXT_INPUT_PRICE_PER_1M",
    "0",
)

OPENAI_TEXT_OUTPUT_PRICE_PER_1M = get_price_per_1m_tokens(
    "OPENAI_TEXT_OUTPUT_PRICE_PER_1M",
    "0",
)

OPENAI_AUDIO_INPUT_PRICE_PER_1M = get_price_per_1m_tokens(
    "OPENAI_AUDIO_INPUT_PRICE_PER_1M",
    "0",
)

OPENAI_AUDIO_OUTPUT_PRICE_PER_1M = get_price_per_1m_tokens(
    "OPENAI_AUDIO_OUTPUT_PRICE_PER_1M",
    "0",
)


def create_openai_usage_totals() -> dict:
    return {
        "text_input_tokens": 0,
        "text_output_tokens": 0,
        "audio_input_tokens": 0,
        "audio_output_tokens": 0,
        "raw_events": [],
    }


def get_nested_value(data: dict, path: list[str]) -> Any:
    current = data

    for key in path:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def get_nested_int(data: dict, path: list[str]) -> int:
    return to_int(get_nested_value(data, path))


def extract_realtime_usage_from_event(event: dict) -> dict:
    """
    Extract token usage from an OpenAI Realtime response.done event.

    Expected common shape:
    {
      "type": "response.done",
      "response": {
        "usage": {
          "input_tokens": ...,
          "output_tokens": ...,
          "input_token_details": {
            "text_tokens": ...,
            "audio_tokens": ...
          },
          "output_token_details": {
            "text_tokens": ...,
            "audio_tokens": ...
          }
        }
      }
    }

    This function is defensive because the usage shape can vary.
    """

    usage = (
        get_nested_value(event, ["response", "usage"])
        or event.get("usage")
        or {}
    )

    input_details = usage.get("input_token_details") or {}
    output_details = usage.get("output_token_details") or {}

    text_input_tokens = (
        get_nested_int(usage, ["input_token_details", "text_tokens"])
        or to_int(input_details.get("text_tokens"))
    )

    audio_input_tokens = (
        get_nested_int(usage, ["input_token_details", "audio_tokens"])
        or to_int(input_details.get("audio_tokens"))
    )

    text_output_tokens = (
        get_nested_int(usage, ["output_token_details", "text_tokens"])
        or to_int(output_details.get("text_tokens"))
    )

    audio_output_tokens = (
        get_nested_int(usage, ["output_token_details", "audio_tokens"])
        or to_int(output_details.get("audio_tokens"))
    )

    input_tokens = to_int(usage.get("input_tokens"))
    output_tokens = to_int(usage.get("output_tokens"))

    # Fallback:
    # If API only gives total input/output tokens and no audio/text split,
    # store them as text tokens so usage is not lost.
    if not text_input_tokens and not audio_input_tokens and input_tokens:
        text_input_tokens = input_tokens

    if not text_output_tokens and not audio_output_tokens and output_tokens:
        text_output_tokens = output_tokens

    return {
        "text_input_tokens": text_input_tokens,
        "text_output_tokens": text_output_tokens,
        "audio_input_tokens": audio_input_tokens,
        "audio_output_tokens": audio_output_tokens,
        "raw_usage": usage,
    }


def add_usage_to_totals(totals: dict, usage: dict) -> dict:
    totals["text_input_tokens"] += to_int(usage.get("text_input_tokens"))
    totals["text_output_tokens"] += to_int(usage.get("text_output_tokens"))
    totals["audio_input_tokens"] += to_int(usage.get("audio_input_tokens"))
    totals["audio_output_tokens"] += to_int(usage.get("audio_output_tokens"))

    raw_usage = usage.get("raw_usage")
    if raw_usage:
        totals.setdefault("raw_events", []).append(raw_usage)

    return totals


def track_realtime_response_done(totals: dict, event: dict) -> dict:
    usage = extract_realtime_usage_from_event(event)
    add_usage_to_totals(totals, usage)
    return build_openai_usage_snapshot(totals)


def calculate_openai_cost_usd(totals: dict) -> float:
    text_input_cost = (
        to_int(totals.get("text_input_tokens")) / 1_000_000
    ) * OPENAI_TEXT_INPUT_PRICE_PER_1M

    text_output_cost = (
        to_int(totals.get("text_output_tokens")) / 1_000_000
    ) * OPENAI_TEXT_OUTPUT_PRICE_PER_1M

    audio_input_cost = (
        to_int(totals.get("audio_input_tokens")) / 1_000_000
    ) * OPENAI_AUDIO_INPUT_PRICE_PER_1M

    audio_output_cost = (
        to_int(totals.get("audio_output_tokens")) / 1_000_000
    ) * OPENAI_AUDIO_OUTPUT_PRICE_PER_1M

    return round(
        text_input_cost
        + text_output_cost
        + audio_input_cost
        + audio_output_cost,
        6,
    )


def build_openai_usage_snapshot(totals: dict) -> dict:
    return {
        "text_input_tokens": to_int(totals.get("text_input_tokens")),
        "text_output_tokens": to_int(totals.get("text_output_tokens")),
        "audio_input_tokens": to_int(totals.get("audio_input_tokens")),
        "audio_output_tokens": to_int(totals.get("audio_output_tokens")),
        "openai_cost_usd": calculate_openai_cost_usd(totals),
    }


def build_openai_usage_json(
    totals: dict,
    model: str | None = None,
    extra: dict | None = None,
) -> dict:
    payload = {
        "model": model,
        "text_input_tokens": to_int(totals.get("text_input_tokens")),
        "text_output_tokens": to_int(totals.get("text_output_tokens")),
        "audio_input_tokens": to_int(totals.get("audio_input_tokens")),
        "audio_output_tokens": to_int(totals.get("audio_output_tokens")),
        "openai_cost_usd": calculate_openai_cost_usd(totals),
        "price_per_1m": {
            "text_input": OPENAI_TEXT_INPUT_PRICE_PER_1M,
            "text_output": OPENAI_TEXT_OUTPUT_PRICE_PER_1M,
            "audio_input": OPENAI_AUDIO_INPUT_PRICE_PER_1M,
            "audio_output": OPENAI_AUDIO_OUTPUT_PRICE_PER_1M,
        },
        "raw_events": totals.get("raw_events") or [],
    }

    if extra:
        payload.update(extra)

    return payload


def build_call_usage_update(
    totals: dict,
    model: str | None = None,
    extra_usage: dict | None = None,
) -> dict:
    snapshot = build_openai_usage_snapshot(totals)

    return {
        "text_input_tokens": snapshot["text_input_tokens"],
        "text_output_tokens": snapshot["text_output_tokens"],
        "audio_input_tokens": snapshot["audio_input_tokens"],
        "audio_output_tokens": snapshot["audio_output_tokens"],
        "openai_cost_usd": snapshot["openai_cost_usd"],
        "openai_usage": build_openai_usage_json(
            totals=totals,
            model=model,
            extra=extra_usage,
        ),
    }


def persist_call_openai_usage(
    call_id: str | None,
    totals: dict,
    update_call_func: Callable[[str, dict], Any],
    model: str | None = None,
    extra_updates: dict | None = None,
    extra_usage: dict | None = None,
):
    if not call_id:
        return None

    updates = build_call_usage_update(
        totals=totals,
        model=model,
        extra_usage=extra_usage,
    )

    if extra_updates:
        updates.update(extra_updates)

    return update_call_func(call_id, updates)


def print_usage_summary(prefix: str, totals: dict):
    snapshot = build_openai_usage_snapshot(totals)

    print(
        f"{prefix} | "
        f"text_in={snapshot['text_input_tokens']} "
        f"text_out={snapshot['text_output_tokens']} "
        f"audio_in={snapshot['audio_input_tokens']} "
        f"audio_out={snapshot['audio_output_tokens']} "
        f"cost=${snapshot['openai_cost_usd']}"
    )