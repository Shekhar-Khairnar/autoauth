"""Tool 1 of 5: Coverage Requirements Discovery (Da Vinci CRD).

For the hosted-demo deployment the MCP server runs without a separately
deployed mock payer, so this tool returns a hardcoded coverage decision
rather than HTTP-calling a payer service. The decision is the one the
demo storyline requires: prior authorization IS required and the next
step is to fetch questionnaire `q-mri-lumbar-v1`.
"""
from typing import Any

_HARDCODED_PAYER_NAME = "MockHealth Plan"
_HARDCODED_QUESTIONNAIRE_ID = "q-mri-lumbar-v1"


def run(
    cpt_code: str,
    patient_id: str,
    context: dict | None = None,
) -> dict[str, Any]:
    """Return the hardcoded coverage-discovery decision for the demo workflow.

    Args:
        cpt_code: CPT/HCPCS procedure code, e.g. "72148".
        patient_id: FHIR Patient id, e.g. "mr-johnson-123".
        context: SHARP passthrough dict from Prompt Opinion carrying
            `patient_id`, `fhir_token`, and `practitioner_id`. Accepted on
            every tool so authentication propagation can be turned on
            without changing tool signatures.

    Returns:
        dict with keys:
            - pa_required: bool, True for the demo path.
            - questionnaire_id: str, DTR Questionnaire id to fetch next.
            - payer_name: str, human-readable payer label.
            - summary: str, markdown block for the chat surface.

    Example:
        >>> coverage = run("72148", "mr-johnson-123")
        >>> coverage["pa_required"]
        True
        >>> coverage["questionnaire_id"]
        'q-mri-lumbar-v1'
    """
    pa_required = True
    questionnaire_id = _HARDCODED_QUESTIONNAIRE_ID
    payer_name = _HARDCODED_PAYER_NAME

    chat_summary = (
        f"## Coverage Discovery (CRD)\n\n"
        f"- **Payer:** {payer_name}\n"
        f"- **CPT:** `{cpt_code}`\n"
        f"- **Prior authorization required:** **YES**\n"
        f"- **Questionnaire id:** `{questionnaire_id}`\n\n"
        f"_Next step: call `dtr_fetch_questionnaire` with that id._"
    )

    return {
        "pa_required": pa_required,
        "questionnaire_id": questionnaire_id,
        "payer_name": payer_name,
        "summary": chat_summary,
    }
