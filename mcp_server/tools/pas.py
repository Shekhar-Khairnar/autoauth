"""Tool 4 of 5: Prior Authorization Support submission (Da Vinci PAS).

For the hosted-demo deployment the MCP server runs without a separately
deployed mock payer, so this tool returns a hardcoded adjudication rather
than HTTP-calling a payer service. The deny-then-approve sequence is
preserved via a module-level submission counter keyed by
`(patient_id, cpt_code)`:

    - First submission for the key  -> denied (forces the appeal flow).
    - Subsequent submissions         -> approved with a synthetic auth #.

`appeal_denial` invokes this same `run()` for its internal resubmit, so a
single counter governs both the initial and appeal-resubmit paths.
"""
import time
from typing import Any

# Submission counter keyed by f"{patient_id}_{cpt_code}". Module-level so
# `appeal_denial`'s resubmit and the orchestrator's direct call share state.
_SUBMISSION_COUNTS: dict[str, int] = {}


def run(
    patient_id: str,
    cpt_code: str,
    questionnaire_response: dict[str, Any],
    narrative: str,
    evidence_refs: list[str],
    context: dict | None = None,
) -> dict[str, Any]:
    """Return a hardcoded PA adjudication: deny first, approve thereafter.

    Args:
        patient_id: FHIR Patient id, e.g. "mr-johnson-123".
        cpt_code: CPT procedure code being requested.
        questionnaire_response: linkId -> answer mapping from
            `synthesize_clinical_justification`. Not validated in the demo.
        narrative: Medical-necessity narrative. On a resubmit, this is the
            appeal letter.
        evidence_refs: FHIR resource references cited as supporting evidence.
        context: SHARP passthrough dict from Prompt Opinion carrying
            `patient_id`, `fhir_token`, and `practitioner_id`. Accepted on
            every tool so authentication propagation can be turned on
            without changing tool signatures.

    Returns:
        dict with keys:
            - status: "approved" | "denied".
            - auth_number: str | None, synthetic auth id when approved.
            - denial_reason: str | None, the demo's denial text when denied.
            - summary: markdown block for the chat surface.

    Example:
        >>> first = run("mr-johnson-123", "72148", {}, "narrative", [])
        >>> first["status"]
        'denied'
        >>> second = run("mr-johnson-123", "72148", {}, "appeal", [])
        >>> second["status"]
        'approved'
    """
    submission_key = f"{patient_id}_{cpt_code}"
    _SUBMISSION_COUNTS[submission_key] = _SUBMISSION_COUNTS.get(submission_key, 0) + 1

    if _SUBMISSION_COUNTS[submission_key] == 1:
        status = "denied"
        auth_number = None
        denial_reason = "Insufficient documentation of conservative therapy"
    else:
        status = "approved"
        auth_number = f"MH-AUTH-{int(time.time() % 100000000)}"
        denial_reason = None

    if status == "approved":
        chat_summary = (
            f"## PAS Decision: **APPROVED**\n\n"
            f"- **Patient:** *Patient/{patient_id}*\n"
            f"- **CPT:** `{cpt_code}`\n"
            f"- **Authorization number:** `{auth_number}`\n"
        )
    else:
        chat_summary = (
            f"## PAS Decision: **DENIED**\n\n"
            f"- **Patient:** *Patient/{patient_id}*\n"
            f"- **CPT:** `{cpt_code}`\n"
            f"- **Reason:** {denial_reason}\n\n"
            f"_Next step: call `appeal_denial` with this denial reason._"
        )

    return {
        "status": status,
        "auth_number": auth_number,
        "denial_reason": denial_reason,
        "summary": chat_summary,
    }
