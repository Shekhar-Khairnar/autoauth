"""AutoAuth - AI agents for healthcare prior authorization.

Mock payer service implementing the Da Vinci Burden Reduction endpoints
(CRD, DTR, PAS) used by the AutoAuth orchestrator during demos.

The payer's deny-then-approve behavior on PAS is intentional choreography:
the first submission for any given patient is denied so the agent loop
exercises `appeal_denial`, the GenAI rebuttal tool. The second submission
(the appeal) is approved with a synthetic authorization number.

Compliant with the HL7 Da Vinci IGs referenced by CMS-0057-F (Jan 1, 2026).
"""
import random
import string
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="MockHealth Plan", version="0.1.0")

# Submission counter keyed by FHIR Patient id. Drives the deterministic
# deny-then-approve sequence: first PAS submission denies, second approves.
_SUBMISSION_COUNT: dict[str, int] = {}

CPT_MRI_LUMBAR = "72148"
QUESTIONNAIRE_ID = "q-mri-lumbar-v1"


class CRDRequest(BaseModel):
    """Wire-format body for the CRD coverage-discovery endpoint."""

    cpt_code: str
    patient_id: str


class PASRequest(BaseModel):
    """Wire-format body for the PAS claim-submission endpoint."""

    patient_id: str
    cpt_code: str
    questionnaire_response: dict[str, Any] | None = None
    narrative: str | None = None
    evidence_refs: list[str] | None = None


@app.post("/crd/coverage-discovery")
def coverage_discovery(request: CRDRequest) -> dict[str, Any]:
    """Return whether prior authorization is required for the given CPT.

    Args:
        request: CRDRequest with `cpt_code` and `patient_id`.

    Returns:
        dict with `pa_required` (bool), `questionnaire_id` (str | None) and
        `payer_name` (str). Demo policy requires PA only for CPT 72148.

    Example:
        >>> coverage_discovery(CRDRequest(cpt_code="72148", patient_id="x"))
        {'pa_required': True, 'questionnaire_id': 'q-mri-lumbar-v1', ...}
    """
    if request.cpt_code == CPT_MRI_LUMBAR:
        return {
            "pa_required": True,
            "questionnaire_id": QUESTIONNAIRE_ID,
            "payer_name": "MockHealth Plan",
        }
    return {
        "pa_required": False,
        "questionnaire_id": None,
        "payer_name": "MockHealth Plan",
    }


@app.get("/dtr/questionnaire/{questionnaire_id}")
def get_questionnaire(questionnaire_id: str) -> dict[str, Any]:
    """Return the FHIR Questionnaire associated with this PA decision.

    Args:
        questionnaire_id: Identifier returned by the CRD endpoint. Only
            `q-mri-lumbar-v1` is supported by the demo.

    Returns:
        A FHIR R4 Questionnaire dict whose `item[]` enumerates the four
        evidence items the payer requires: pain duration, conservative
        therapy completion, red-flag symptom screen, prior imaging.

    Raises:
        HTTPException(404): when the questionnaire_id is unknown.

    Example:
        >>> q = get_questionnaire("q-mri-lumbar-v1")
        >>> len(q["item"])
        4
    """
    if questionnaire_id != QUESTIONNAIRE_ID:
        raise HTTPException(404, f"Unknown questionnaire: {questionnaire_id}")
    return {
        "resourceType": "Questionnaire",
        "id": QUESTIONNAIRE_ID,
        "status": "active",
        "title": "MRI Lumbar Spine - Medical Necessity",
        "item": [
            {
                "linkId": "pain-duration",
                "text": "Duration of low back pain in weeks.",
                "type": "integer",
                "required": True,
            },
            {
                "linkId": "conservative-therapy",
                "text": (
                    "Has the patient completed at least 6 weeks of conservative "
                    "therapy (PT, NSAIDs, neuropathic agents)?"
                ),
                "type": "boolean",
                "required": True,
            },
            {
                "linkId": "red-flags",
                "text": (
                    "Are any red-flag symptoms present (cauda equina, fever, "
                    "malignancy history, IV drug use, recent trauma)?"
                ),
                "type": "boolean",
                "required": True,
            },
            {
                "linkId": "prior-imaging",
                "text": "Has lumbar imaging been performed in the last 12 months?",
                "type": "boolean",
                "required": True,
            },
        ],
    }


@app.post("/pas/claim")
def submit_claim(request: PASRequest) -> dict[str, Any]:
    """Adjudicate the PA bundle: first submission denies, second approves.

    The denial -> appeal -> approval cycle is intentional. The first
    submission for any patient returns a denial so the orchestrator must
    invoke `appeal_denial`. The second submission for the same patient
    returns an approval with a synthetic authorization number.

    Args:
        request: PASRequest carrying the patient id, CPT code, answered
            questionnaire, narrative, and evidence references.

    Returns:
        dict with `status` ("approved" | "denied"), `auth_number`
        (str | None), and `denial_reason` (str | None).

    Example:
        >>> first = submit_claim(PASRequest(patient_id="x", cpt_code="72148"))
        >>> first["status"]
        'denied'
        >>> second = submit_claim(PASRequest(patient_id="x", cpt_code="72148"))
        >>> second["status"]
        'approved'
    """
    submission_count = _SUBMISSION_COUNT.get(request.patient_id, 0) + 1
    _SUBMISSION_COUNT[request.patient_id] = submission_count

    if submission_count == 1:
        return {
            "status": "denied",
            "auth_number": None,
            "denial_reason": "Insufficient documentation of conservative therapy",
        }
    auth_number = "MH-AUTH-" + "".join(random.choices(string.digits, k=8))
    return {"status": "approved", "auth_number": auth_number, "denial_reason": None}


@app.post("/admin/reset")
def reset_state() -> dict[str, bool]:
    """Wipe the submission counter so the deny -> approve cycle replays.

    Useful between demo takes when the recording overran or needs another
    cut. Not part of the Da Vinci spec; AutoAuth-specific helper.

    Returns:
        `{"ok": True}` once the in-memory state is cleared.

    Example:
        >>> reset_state()
        {'ok': True}
    """
    _SUBMISSION_COUNT.clear()
    return {"ok": True}
