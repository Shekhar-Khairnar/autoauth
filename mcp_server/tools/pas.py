"""Tool 4 of 5: Prior Authorization Support submission (Da Vinci PAS).

PAS is the actual submit-and-adjudicate step. The orchestrator hands over
the answered Questionnaire, the medical-necessity narrative, and the FHIR
evidence references; the payer returns approved / denied / pending. On
denial, the orchestrator is expected to call `appeal_denial` and re-invoke
this tool with the appeal letter as the new narrative.
"""
from typing import Any

from mcp_server import payer_client


def run(
    patient_id: str,
    cpt_code: str,
    questionnaire_response: dict[str, Any],
    narrative: str,
    evidence_refs: list[str],
    context: dict | None = None,
) -> dict[str, Any]:
    """Submit a completed PA bundle to the payer and return adjudication.

    Sends the payload to the payer's `/pas/claim` endpoint and shapes the
    response into a markdown summary that directs the orchestrator to its
    next move (deliver the auth number, or call `appeal_denial`).

    Args:
        patient_id: FHIR Patient id, e.g. "mr-johnson-123".
        cpt_code: CPT/HCPCS procedure code being requested.
        questionnaire_response: Mapping of Questionnaire `linkId` to answer,
            produced by `synthesize_clinical_justification`.
        narrative: Medical-necessity narrative (markdown). On a resubmission
            after a denial, this should be the appeal letter.
        evidence_refs: FHIR resource references cited as supporting evidence,
            e.g. `["Encounter/enc-pt-456", "MedicationRequest/medreq-ibuprofen-001"]`.
        context: SHARP passthrough dict from Prompt Opinion carrying
            `patient_id`, `fhir_token`, and `practitioner_id`. Accepted on
            every tool so authentication propagation can be turned on
            without changing tool signatures.

    Returns:
        dict with keys:
            - status: str, one of "approved", "denied", "pending".
            - auth_number: str | None, payer-issued authorization number
              when approved.
            - denial_reason: str | None, payer's free-text reason when
              denied.
            - summary: str, markdown block for the chat surface.

    Example:
        >>> decision = run(
        ...     patient_id="mr-johnson-123",
        ...     cpt_code="72148",
        ...     questionnaire_response={"pain-duration": 26, "red-flags": False},
        ...     narrative="Patient has failed >=6 weeks of conservative therapy...",
        ...     evidence_refs=["Encounter/enc-pt-456"],
        ... )
        >>> decision["status"]
        'denied'
        >>> decision["denial_reason"]
        'Insufficient documentation of conservative therapy'
    """
    pas_payload = {
        "patient_id": patient_id,
        "cpt_code": cpt_code,
        "questionnaire_response": questionnaire_response,
        "narrative": narrative,
        "evidence_refs": evidence_refs,
    }
    payer_response = payer_client.pas_call(pas_payload)
    status = payer_response.get("status", "unknown")
    auth_number = payer_response.get("auth_number")
    denial_reason = payer_response.get("denial_reason")

    if status == "approved":
        chat_summary = (
            f"## PAS Decision: **APPROVED**\n\n"
            f"- **Patient:** *Patient/{patient_id}*\n"
            f"- **CPT:** `{cpt_code}`\n"
            f"- **Authorization number:** `{auth_number}`\n"
        )
    elif status == "denied":
        chat_summary = (
            f"## PAS Decision: **DENIED**\n\n"
            f"- **Patient:** *Patient/{patient_id}*\n"
            f"- **CPT:** `{cpt_code}`\n"
            f"- **Reason:** {denial_reason}\n\n"
            f"_Next step: call `appeal_denial` with this denial reason, then "
            f"resubmit via `pas_submit_bundle` with the appeal letter._"
        )
    else:
        chat_summary = f"## PAS Decision: {status.upper()}\n\nUnexpected status from payer."

    return {
        "status": status,
        "auth_number": auth_number,
        "denial_reason": denial_reason,
        "summary": chat_summary,
    }
