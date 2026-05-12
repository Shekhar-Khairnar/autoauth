"""Tool 3 of 5 (GenAI): synthesize the clinical justification.

This is the first of AutoAuth's two GenAI tools. It pulls the patient's full
FHIR chart, hands the chart plus the payer's Questionnaire to an LLM, and
asks the model to produce three artifacts at once:

1. Concrete answers to each Questionnaire item, in the item's declared type.
2. A markdown medical-necessity narrative that cites specific FHIR resources.
3. An explicit list of every FHIR reference the narrative relied on.

The prompt is held in `mcp_server/prompts/synthesize_system.md` and is read
on every call so it can be tuned without a server restart.
"""
import json
from pathlib import Path
from typing import Any

from mcp_server import fhir_client, llm_client

_SYNTHESIZE_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "synthesize_system.md"
)
_REQUIRED_OUTPUT_KEYS = ("answers", "narrative", "evidence_refs")


def _load_system_prompt() -> str:
    """Read the synthesize system prompt from disk on every call.

    Reading on each invocation (instead of caching at import time) lets the
    operator edit the prompt file between calls without restarting the MCP
    server -- valuable during demo rehearsals.

    Returns:
        The full system prompt as a UTF-8 string.

    Example:
        >>> system_prompt = _load_system_prompt()
        >>> "board-certified clinical reviewer" in system_prompt
        True
    """
    return _SYNTHESIZE_PROMPT_PATH.read_text(encoding="utf-8")


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
        dict with at least the keys `answers`, `narrative`, `evidence_refs`.

    Example:
        >>> _parse_llm_output('{"answers":{},"narrative":"...","evidence_refs":[]}')
        {'answers': {}, 'narrative': '...', 'evidence_refs': []}
    """
    parsed = json.loads(_strip_code_fences(raw_json))
    missing_keys = [key for key in _REQUIRED_OUTPUT_KEYS if key not in parsed]
    if missing_keys:
        raise ValueError(f"LLM JSON missing keys: {missing_keys}")
    return parsed


def _build_summary(narrative: str, evidence_refs: list[str]) -> str:
    """Format the LLM's narrative and citations as a chat-ready markdown block.

    Args:
        narrative: Medical-necessity narrative in markdown.
        evidence_refs: FHIR resource references to render as a bulleted list.

    Returns:
        A markdown string with a level-2 heading, the narrative body, and a
        bulleted, italicized evidence list.

    Example:
        >>> block = _build_summary("Patient...", ["Encounter/enc-pt-456"])
        >>> "Medical-Necessity Narrative" in block
        True
    """
    evidence_bullets = (
        "\n".join(f"- *{reference}*" for reference in evidence_refs)
        or "- _(none cited)_"
    )
    return (
        f"## Medical-Necessity Narrative\n\n{narrative}\n\n"
        f"**Evidence cited:**\n{evidence_bullets}"
    )


def run(
    patient_id: str,
    cpt_code: str,
    questionnaire: dict[str, Any],
    context: dict | None = None,
) -> dict[str, Any]:
    """Generate a payer-ready clinical justification from a patient's FHIR data.

    Reads the patient's full FHIR bundle from the configured FHIR server,
    extracts the relevant clinical evidence, and synthesizes a
    medical-necessity narrative that directly answers each item in the
    payer's Questionnaire. Every clinical claim is grounded in a specific
    FHIR resource reference. On a malformed JSON response, retries the LLM
    call once with a "return JSON only" follow-up.

    Args:
        patient_id: FHIR Patient id, e.g. "mr-johnson-123".
        cpt_code: CPT code for the requested service, e.g. "72148".
        questionnaire: FHIR R4 Questionnaire returned by
            `dtr_fetch_questionnaire`.
        context: SHARP passthrough dict from Prompt Opinion carrying
            `patient_id`, `fhir_token`, and `practitioner_id`. Accepted on
            every tool so authentication propagation can be turned on
            without changing tool signatures.

    Returns:
        dict with keys:
            - answers: dict mapping each Questionnaire `linkId` to a
              concrete answer (string, integer, or boolean per item type).
            - narrative: str, markdown clinical justification with inline
              FHIR-resource citations in italics.
            - evidence_refs: list[str] of FHIR references cited in the
              narrative, each in `ResourceType/id` form.
            - summary: str, markdown block combining narrative + citations
              for chat display.

    Example:
        >>> justification = run(
        ...     patient_id="mr-johnson-123",
        ...     cpt_code="72148",
        ...     questionnaire={
        ...         "resourceType": "Questionnaire",
        ...         "id": "q-mri-lumbar-v1",
        ...         "item": [{"linkId": "pain-duration", "type": "integer"}],
        ...     },
        ... )
        >>> justification["answers"]["pain-duration"]
        26
        >>> "Encounter/enc-pt-456" in justification["evidence_refs"]
        True
    """
    patient_bundle = fhir_client.get_patient_bundle(patient_id)
    system_prompt = _load_system_prompt()
    user_payload = json.dumps(
        {"cpt_code": cpt_code, "questionnaire": questionnaire, "bundle": patient_bundle}
    )
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
        print(f"[synthesize] first parse failed ({parse_error}); retrying once")
        chat_messages.append({"role": "assistant", "content": raw_response})
        chat_messages.append({
            "role": "user",
            "content": (
                "Your previous output was not valid JSON. Return ONLY a JSON "
                "object with keys answers, narrative, evidence_refs."
            ),
        })
        raw_response = llm_client.chat(
            chat_messages, response_format={"type": "json_object"}
        )
        parsed_result = _parse_llm_output(raw_response)

    return {
        "answers": parsed_result["answers"],
        "narrative": parsed_result["narrative"],
        "evidence_refs": parsed_result["evidence_refs"],
        "summary": _build_summary(
            parsed_result["narrative"], parsed_result["evidence_refs"]
        ),
    }
