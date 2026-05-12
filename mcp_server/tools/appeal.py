"""Tool 5 of 5 (GenAI): draft an appeal letter from the denial reason.

The second of AutoAuth's two GenAI tools. After a PAS denial the
orchestrator hands the payer's free-text denial reason plus the originally
submitted narrative back to the LLM. The model re-reads the FHIR bundle,
identifies the specific evidence that rebuts the denial, and drafts a
formal appeal letter that the orchestrator then resubmits via PAS.

The prompt is held in `mcp_server/prompts/appeal_system.md` and is read on
every call so it can be tuned without a server restart.
"""
import json
from pathlib import Path
from typing import Any

from mcp_server import fhir_client, llm_client

_APPEAL_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "appeal_system.md"
)
_REQUIRED_OUTPUT_KEYS = ("appeal_letter", "additional_evidence_refs")


def _load_system_prompt() -> str:
    """Read the appeal system prompt from disk on every call.

    Returns:
        The full system prompt as a UTF-8 string.

    Example:
        >>> system_prompt = _load_system_prompt()
        >>> "appeals specialist" in system_prompt
        True
    """
    return _APPEAL_PROMPT_PATH.read_text(encoding="utf-8")


def _strip_code_fences(text: str) -> str:
    """Strip ```json / ``` wrappers some providers add even in JSON mode.

    Anthropic models served through OpenRouter sometimes wrap their JSON
    response in ```json ... ``` fences even when `response_format` is set
    to `json_object`. This helper makes parsing robust to that.

    Args:
        text: Raw assistant content.

    Returns:
        The content with any surrounding triple-backtick fences removed.

    Example:
        >>> _strip_code_fences('```json\\n{"ok": true}\\n```')
        '{"ok": true}'
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        stripped = stripped[first_newline + 1:] if first_newline != -1 else stripped[3:]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    return stripped.strip()


def _parse_llm_output(raw_json: str) -> dict[str, Any]:
    """Parse the LLM's JSON response and assert the required keys are present.

    Args:
        raw_json: Raw assistant content. Must be a JSON object string,
            optionally wrapped in markdown code fences.

    Returns:
        dict with at least the keys `appeal_letter` and
        `additional_evidence_refs`.

    Example:
        >>> _parse_llm_output('{"appeal_letter":"...","additional_evidence_refs":[]}')
        {'appeal_letter': '...', 'additional_evidence_refs': []}
    """
    parsed = json.loads(_strip_code_fences(raw_json))
    missing_keys = [key for key in _REQUIRED_OUTPUT_KEYS if key not in parsed]
    if missing_keys:
        raise ValueError(f"LLM JSON missing keys: {missing_keys}")
    return parsed


def _build_summary(appeal_letter: str, evidence_refs: list[str]) -> str:
    """Format the appeal letter and citations as a chat-ready markdown block.

    Args:
        appeal_letter: Markdown appeal letter body.
        evidence_refs: Additional FHIR resource references cited in the letter.

    Returns:
        A markdown string with a level-2 heading, the letter body, and a
        bulleted, italicized evidence list.

    Example:
        >>> block = _build_summary("Dear Medical Director...", ["Encounter/enc-pt-456"])
        >>> block.startswith("## Appeal Letter")
        True
    """
    evidence_bullets = (
        "\n".join(f"- *{reference}*" for reference in evidence_refs)
        or "- _(none cited)_"
    )
    return (
        f"## Appeal Letter\n\n{appeal_letter}\n\n"
        f"**Additional evidence cited:**\n{evidence_bullets}"
    )


def run(
    patient_id: str,
    denial_reason: str,
    original_narrative: str,
    context: dict | None = None,
) -> dict[str, Any]:
    """Draft a formal appeal letter that rebuts the payer's denial reason.

    Re-fetches the patient's FHIR chart, hands the chart along with the
    denial reason and original narrative to the LLM, and returns a structured
    appeal letter plus the specific FHIR evidence references it relies on.
    On malformed JSON, retries the LLM call once with a "return JSON only"
    follow-up.

    Args:
        patient_id: FHIR Patient id, e.g. "mr-johnson-123".
        denial_reason: Free-text denial reason returned by `pas_submit_bundle`.
        original_narrative: The narrative originally submitted to PAS, so
            the model can address what was missed rather than repeat it.
        context: SHARP passthrough dict from Prompt Opinion carrying
            `patient_id`, `fhir_token`, and `practitioner_id`. Accepted on
            every tool so authentication propagation can be turned on
            without changing tool signatures.

    Returns:
        dict with keys:
            - appeal_letter: str, markdown appeal letter body addressed to
              the payer's Medical Director.
            - additional_evidence_refs: list[str] of FHIR resource
              references newly cited in the letter, each in
              `ResourceType/id` form.
            - summary: str, markdown block combining letter + citations
              for chat display.

    Example:
        >>> appeal = run(
        ...     patient_id="mr-johnson-123",
        ...     denial_reason="Insufficient documentation of conservative therapy",
        ...     original_narrative="Patient is a 58 year old male with chronic LBP...",
        ... )
        >>> appeal["appeal_letter"].startswith("Dear")
        True
        >>> "MedicationRequest/medreq-ibuprofen-001" in appeal["additional_evidence_refs"]
        True
    """
    patient_bundle = fhir_client.get_patient_bundle(patient_id)
    system_prompt = _load_system_prompt()
    user_payload = json.dumps({
        "denial_reason": denial_reason,
        "original_narrative": original_narrative,
        "bundle": patient_bundle,
    })
    chat_messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_payload},
    ]

    raw_response = llm_client.chat(
        chat_messages, response_format={"type": "json_object"}
    )
    try:
        parsed_result = _parse_llm_output(raw_response)
    except (json.JSONDecodeError, ValueError) as parse_error:
        print(f"[appeal] first parse failed ({parse_error}); retrying once")
        chat_messages.append({"role": "assistant", "content": raw_response})
        chat_messages.append({
            "role": "user",
            "content": (
                "Your previous output was not valid JSON. Return ONLY a JSON "
                "object with keys appeal_letter, additional_evidence_refs."
            ),
        })
        raw_response = llm_client.chat(
            chat_messages, response_format={"type": "json_object"}
        )
        parsed_result = _parse_llm_output(raw_response)

    return {
        "appeal_letter": parsed_result["appeal_letter"],
        "additional_evidence_refs": parsed_result["additional_evidence_refs"],
        "summary": _build_summary(
            parsed_result["appeal_letter"], parsed_result["additional_evidence_refs"]
        ),
    }
