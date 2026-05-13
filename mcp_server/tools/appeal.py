"""Tool 5 of 5 (GenAI): draft an appeal letter AND resubmit to the payer.

The second of AutoAuth's two GenAI tools. After a PAS denial, the
orchestrator hands the payer's denial reason plus the originally submitted
narrative back to this tool. The tool:

  1. Re-reads the patient's FHIR bundle.
  2. Asks the LLM to draft a formal appeal letter that specifically rebuts
     the denial reason with FHIR-grounded evidence.
  3. Immediately resubmits the appeal letter to the payer's PAS endpoint
     using the original questionnaire response and the combined evidence
     references.
  4. Returns the appeal letter, the cited evidence, and the payer's final
     adjudication (auth number on approval, denial reason on second denial).

Consolidating the appeal-then-resubmit pair into a single tool keeps the
orchestrator's tool-call chain short (5 calls total in the deny-then-approve
case), which matters for smaller orchestrator LLMs that drop off after long
multi-step sequences.

The system prompt for the appeal drafting step lives in
`mcp_server/prompts/appeal_system.md` and is read on every call so it can be
tuned without a server restart.
"""
import json
from pathlib import Path
from typing import Any

from mcp_server import fhir_client, llm_client
from mcp_server.tools import pas as pas_tool

_APPEAL_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "appeal_system.md"
)
_REQUIRED_LLM_KEYS = ("appeal_letter", "additional_evidence_refs")


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
    missing_keys = [key for key in _REQUIRED_LLM_KEYS if key not in parsed]
    if missing_keys:
        raise ValueError(f"LLM JSON missing keys: {missing_keys}")
    return parsed


def _generate_appeal_letter(
    patient_bundle: dict[str, Any],
    denial_reason: str,
    original_narrative: str,
) -> dict[str, Any]:
    """Drive the LLM to produce a structured appeal letter.

    Args:
        patient_bundle: FHIR Bundle for the patient (Patient + chart resources).
        denial_reason: Free-text denial reason from the payer's first PAS pass.
        original_narrative: Narrative that was submitted with the first PAS call.

    Returns:
        dict with keys `appeal_letter` (markdown) and
        `additional_evidence_refs` (list of FHIR refs).

    Example:
        >>> result = _generate_appeal_letter({"resourceType": "Bundle"}, "Reason", "Narrative")
        >>> "appeal_letter" in result and "additional_evidence_refs" in result
        True
    """
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
        return _parse_llm_output(raw_response)
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
        retry_response = llm_client.chat(
            chat_messages, response_format={"type": "json_object"}
        )
        return _parse_llm_output(retry_response)


def _resubmit_to_payer(
    patient_id: str,
    cpt_code: str,
    questionnaire_response: dict[str, Any],
    appeal_letter: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    """Send the appeal back to the payer's PAS endpoint.

    Routes through `pas_tool.run()` so both the initial submission and the
    appeal-resubmit share the same hardcoded deny-then-approve counter for
    the cloud-deploy build. The returned dict keeps only the wire-level
    keys (`status`, `auth_number`, `denial_reason`) so this helper stays a
    drop-in replacement for the previous HTTP call.

    Args:
        patient_id: FHIR Patient id.
        cpt_code: CPT procedure code.
        questionnaire_response: Original linkId -> answer mapping from
            `synthesize_clinical_justification`.
        appeal_letter: Markdown appeal letter to send as the new narrative.
        evidence_refs: Combined evidence references (original + appeal-added).

    Returns:
        Payer adjudication dict with `status`, `auth_number`, `denial_reason`.

    Example:
        >>> verdict = _resubmit_to_payer("mr-johnson-123", "72148", {}, "Dear...", [])
        >>> verdict["status"] in {"approved", "denied", "pending"}
        True
    """
    pas_result = pas_tool.run(
        patient_id,
        cpt_code,
        questionnaire_response,
        appeal_letter,
        evidence_refs,
    )
    return {
        "status": pas_result.get("status"),
        "auth_number": pas_result.get("auth_number"),
        "denial_reason": pas_result.get("denial_reason"),
    }


def _build_summary(
    appeal_letter: str,
    additional_evidence_refs: list[str],
    final_status: str,
    auth_number: str | None,
    final_denial_reason: str | None,
    patient_id: str,
    cpt_code: str,
) -> str:
    """Render the appeal letter + final adjudication as a chat-ready markdown block.

    Args:
        appeal_letter: Markdown appeal letter body.
        additional_evidence_refs: FHIR refs the letter cites.
        final_status: "approved" | "denied" | "pending" from the resubmit.
        auth_number: Payer-issued authorization id when approved.
        final_denial_reason: Payer's reason if denied again.
        patient_id: FHIR Patient id (for the final summary line).
        cpt_code: CPT procedure code (for the final summary line).

    Returns:
        Markdown block combining the appeal letter, the cited evidence, and
        the final adjudication.

    Example:
        >>> block = _build_summary(
        ...     "Dear Medical Director...", ["Encounter/enc-pt-456"],
        ...     "approved", "MH-AUTH-12345678", None,
        ...     "mr-johnson-123", "72148",
        ... )
        >>> "Resubmission Outcome" in block and "APPROVED" in block
        True
    """
    evidence_bullets = (
        "\n".join(f"- *{reference}*" for reference in additional_evidence_refs)
        or "- _(none cited)_"
    )

    if final_status == "approved":
        outcome_block = (
            f"## Resubmission Outcome: **APPROVED**\n\n"
            f"- **Patient:** *Patient/{patient_id}*\n"
            f"- **CPT:** `{cpt_code}`\n"
            f"- **Authorization number:** `{auth_number}`\n\n"
            f"_Initial denial overturned by this automated appeal._"
        )
    elif final_status == "denied":
        outcome_block = (
            f"## Resubmission Outcome: **DENIED (second pass)**\n\n"
            f"- **Patient:** *Patient/{patient_id}*\n"
            f"- **CPT:** `{cpt_code}`\n"
            f"- **Reason:** {final_denial_reason}\n\n"
            f"_Escalate to peer-to-peer review with the payer's medical director._"
        )
    else:
        outcome_block = (
            f"## Resubmission Outcome: {final_status.upper() if final_status else 'UNKNOWN'}"
        )

    return (
        f"## Appeal Letter\n\n{appeal_letter}\n\n"
        f"**Additional evidence cited:**\n{evidence_bullets}\n\n"
        f"---\n\n{outcome_block}"
    )


def run(
    patient_id: str,
    cpt_code: str,
    denial_reason: str,
    original_narrative: str,
    questionnaire_response: dict[str, Any],
    original_evidence_refs: list[str],
    context: dict | None = None,
) -> dict[str, Any]:
    """Draft a formal appeal letter and immediately resubmit it to the payer.

    Performs three operations in a single tool call to keep the
    orchestrator's tool-call chain short:

      1. Re-fetch the patient's FHIR bundle.
      2. Use the LLM to draft an appeal letter that specifically rebuts the
         payer's denial reason with FHIR-grounded evidence.
      3. Resubmit the appeal letter to the payer's PAS endpoint with the
         original questionnaire response and the merged evidence list.

    Args:
        patient_id: FHIR Patient id, e.g. "mr-johnson-123".
        cpt_code: CPT/HCPCS procedure code, e.g. "72148".
        denial_reason: Free-text denial reason returned by
            `pas_submit_bundle` on the first submission.
        original_narrative: Narrative originally submitted to PAS, so the
            model can address what was missed rather than repeat it.
        questionnaire_response: linkId -> answer mapping from the original
            `synthesize_clinical_justification` call; re-sent on the
            resubmit so the payer sees a complete bundle.
        original_evidence_refs: FHIR references cited in the original
            submission; merged with the appeal-added refs on resubmit.
        context: SHARP passthrough dict from Prompt Opinion carrying
            `patient_id`, `fhir_token`, and `practitioner_id`. Accepted on
            every tool so authentication propagation can be turned on
            without changing tool signatures.

    Returns:
        dict with keys:
            - appeal_letter: str, markdown appeal letter body.
            - additional_evidence_refs: list[str], FHIR refs newly cited in
              the appeal letter.
            - final_status: str, "approved" | "denied" | "pending" from the
              resubmit.
            - auth_number: str | None, payer-issued authorization when
              the resubmit is approved.
            - final_denial_reason: str | None, payer's reason on a second
              denial.
            - summary: str, markdown block combining letter, citations, and
              final adjudication for chat display.

    Example:
        >>> appeal = run(
        ...     patient_id="mr-johnson-123",
        ...     cpt_code="72148",
        ...     denial_reason="Insufficient documentation of conservative therapy",
        ...     original_narrative="Patient is a 58 year old male...",
        ...     questionnaire_response={"pain-duration": 26, "red-flags": False},
        ...     original_evidence_refs=["Encounter/enc-pt-456"],
        ... )
        >>> appeal["final_status"]
        'approved'
        >>> appeal["auth_number"].startswith("MH-AUTH-")
        True
    """
    patient_bundle = fhir_client.get_patient_bundle(patient_id)
    appeal_result = _generate_appeal_letter(
        patient_bundle, denial_reason, original_narrative
    )
    appeal_letter = appeal_result["appeal_letter"]
    additional_evidence_refs = appeal_result["additional_evidence_refs"]

    combined_evidence_refs = list(
        dict.fromkeys(list(original_evidence_refs) + list(additional_evidence_refs))
    )
    payer_verdict = _resubmit_to_payer(
        patient_id, cpt_code, questionnaire_response, appeal_letter, combined_evidence_refs
    )
    final_status = payer_verdict.get("status", "unknown")
    auth_number = payer_verdict.get("auth_number")
    final_denial_reason = payer_verdict.get("denial_reason")

    return {
        "appeal_letter": appeal_letter,
        "additional_evidence_refs": additional_evidence_refs,
        "final_status": final_status,
        "auth_number": auth_number,
        "final_denial_reason": final_denial_reason,
        "summary": _build_summary(
            appeal_letter,
            additional_evidence_refs,
            final_status,
            auth_number,
            final_denial_reason,
            patient_id,
            cpt_code,
        ),
    }
