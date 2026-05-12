"""Tool 1 of 5: Coverage Requirements Discovery (Da Vinci CRD).

CRD is the entry point of the Burden Reduction workflow. The provider's
system asks the payer "is prior authorization required for this CPT on this
patient, and if so which Questionnaire should I fetch?". This module wraps
that interaction and shapes the answer for chat display.
"""
from typing import Any

from mcp_server import payer_client


def run(
    cpt_code: str,
    patient_id: str,
    context: dict | None = None,
) -> dict[str, Any]:
    """Determine whether prior authorization is required for a CPT + patient.

    Calls the payer's `/crd/coverage-discovery` endpoint and returns both the
    structured decision and a markdown summary suitable for direct display in
    the orchestrator's chat UI.

    Args:
        cpt_code: CPT/HCPCS procedure code, e.g. "72148" for MRI lumbar spine.
        patient_id: FHIR Patient id, e.g. "mr-johnson-123".
        context: SHARP passthrough dict from Prompt Opinion carrying
            `patient_id`, `fhir_token`, and `practitioner_id`. Accepted on
            every tool so authentication propagation can be turned on
            without changing tool signatures.

    Returns:
        dict with keys:
            - pa_required: bool, True when prior authorization is required.
            - questionnaire_id: str | None, DTR Questionnaire id to fetch
              next when `pa_required` is True; None otherwise.
            - payer_name: str, human-readable payer label.
            - summary: str, markdown block for the chat surface.

    Example:
        >>> coverage = run("72148", "mr-johnson-123")
        >>> coverage["pa_required"]
        True
        >>> coverage["questionnaire_id"]
        'q-mri-lumbar-v1'
        >>> print(coverage["summary"].splitlines()[0])
        ## Coverage Discovery (CRD)
    """
    payer_response = payer_client.crd_call(cpt_code, patient_id)
    pa_required = bool(payer_response.get("pa_required"))
    questionnaire_id = payer_response.get("questionnaire_id")
    payer_name = payer_response.get("payer_name", "Unknown Payer")

    if pa_required:
        chat_summary = (
            f"## Coverage Discovery (CRD)\n\n"
            f"- **Payer:** {payer_name}\n"
            f"- **CPT:** `{cpt_code}`\n"
            f"- **Prior authorization required:** **YES**\n"
            f"- **Questionnaire id:** `{questionnaire_id}`\n\n"
            f"_Next step: call `dtr_fetch_questionnaire` with that id._"
        )
    else:
        chat_summary = (
            f"## Coverage Discovery (CRD)\n\n"
            f"- **Payer:** {payer_name}\n"
            f"- **CPT:** `{cpt_code}`\n"
            f"- **Prior authorization required:** **NO**\n\n"
            f"_Proceed with the order; no PA workflow needed._"
        )

    return {
        "pa_required": pa_required,
        "questionnaire_id": questionnaire_id,
        "payer_name": payer_name,
        "summary": chat_summary,
    }
