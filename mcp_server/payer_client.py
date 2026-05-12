"""Payer-side HTTP client for AutoAuth.

Thin wrappers around the three Da Vinci endpoints (CRD, DTR, PAS) exposed by
the mock payer service. The base URL is read from PAYER_BASE_URL so the same
code works against the local FastAPI mock during demos and against a real
payer in production.
"""
import os
from typing import Any

import requests

_DEFAULT_BASE_URL = "http://localhost:8081"
_CRD_TIMEOUT_SECONDS = 15
_DTR_TIMEOUT_SECONDS = 15
_PAS_TIMEOUT_SECONDS = 30


def _base_url() -> str:
    """Return the payer base URL with any trailing slash stripped.

    Returns:
        Base URL string for the payer service, e.g. `http://localhost:8081`.

    Example:
        >>> os.environ["PAYER_BASE_URL"] = "https://payer.example.org/"
        >>> _base_url()
        'https://payer.example.org'
    """
    return os.getenv("PAYER_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def crd_call(cpt_code: str, patient_id: str) -> dict[str, Any]:
    """Invoke the payer's Coverage Requirements Discovery endpoint.

    Implements the Da Vinci CRD interaction: ask the payer whether prior
    authorization is required for the requested procedure and, if so, which
    DTR Questionnaire to fetch next.

    Args:
        cpt_code: CPT/HCPCS procedure code, e.g. "72148" for MRI lumbar
            spine without contrast.
        patient_id: FHIR Patient id, e.g. "mr-johnson-123".

    Returns:
        Decoded JSON dict with keys `pa_required` (bool), `questionnaire_id`
        (str | None), and `payer_name` (str).

    Example:
        >>> coverage = crd_call("72148", "mr-johnson-123")
        >>> coverage["pa_required"]
        True
        >>> coverage["questionnaire_id"]
        'q-mri-lumbar-v1'
    """
    response = requests.post(
        f"{_base_url()}/crd/coverage-discovery",
        json={"cpt_code": cpt_code, "patient_id": patient_id},
        timeout=_CRD_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def dtr_call(questionnaire_id: str) -> dict[str, Any]:
    """Fetch the payer's DTR Questionnaire for a known questionnaire id.

    Implements the Da Vinci DTR interaction: download the structured
    Questionnaire resource that lists the evidence the payer wants
    answered before the PA can be adjudicated.

    Args:
        questionnaire_id: Identifier returned by `crd_call`, e.g.
            "q-mri-lumbar-v1".

    Returns:
        A FHIR R4 Questionnaire resource as a dict, with `item[]` enumerating
        the structured questions.

    Example:
        >>> questionnaire = dtr_call("q-mri-lumbar-v1")
        >>> questionnaire["resourceType"]
        'Questionnaire'
        >>> len(questionnaire["item"])
        4
    """
    response = requests.get(
        f"{_base_url()}/dtr/questionnaire/{questionnaire_id}",
        timeout=_DTR_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def pas_call(payload: dict[str, Any]) -> dict[str, Any]:
    """Submit a completed PA bundle to the payer's PAS endpoint.

    Implements the Da Vinci PAS interaction: send the answered Questionnaire,
    the medical-necessity narrative, and the supporting FHIR evidence
    references; receive the payer's adjudication.

    Args:
        payload: dict carrying `patient_id`, `cpt_code`,
            `questionnaire_response`, `narrative`, and `evidence_refs`.

    Returns:
        Decoded JSON dict with keys `status` ("approved" | "denied" |
        "pending"), `auth_number` (str | None), and `denial_reason`
        (str | None).

    Example:
        >>> decision = pas_call({
        ...     "patient_id": "mr-johnson-123",
        ...     "cpt_code": "72148",
        ...     "questionnaire_response": {"pain-duration": 26},
        ...     "narrative": "Patient has failed conservative therapy...",
        ...     "evidence_refs": ["Encounter/enc-pt-456"],
        ... })
        >>> decision["status"] in {"approved", "denied", "pending"}
        True
    """
    response = requests.post(
        f"{_base_url()}/pas/claim", json=payload, timeout=_PAS_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response.json()
