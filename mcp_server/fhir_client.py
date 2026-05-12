"""FHIR REST client for AutoAuth.

A deliberately thin HTTP wrapper around the FHIR R4 REST API exposed by the
public HAPI test server. We avoid an opinionated FHIR SDK because FHIR
responses are already JSON and the wire-level visibility helps debugging
during demos. Configure the base URL via FHIR_BASE_URL.
"""
import os
from typing import Any

import requests

_DEFAULT_BASE_URL = "https://hapi.fhir.org/baseR4"
_FHIR_JSON_HEADERS = {"Accept": "application/fhir+json"}
_DEFAULT_TIMEOUT_SECONDS = 30
_EVERYTHING_TIMEOUT_SECONDS = 60


def _base_url() -> str:
    """Return the FHIR server base URL with any trailing slash stripped.

    Returns:
        Base URL string suitable for prefix concatenation, e.g.
        `https://hapi.fhir.org/baseR4` (never with a trailing `/`).

    Example:
        >>> os.environ["FHIR_BASE_URL"] = "https://example.org/r4/"
        >>> _base_url()
        'https://example.org/r4'
    """
    return os.getenv("FHIR_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def get_resource(resource_type: str, resource_id: str) -> dict[str, Any]:
    """Fetch a single FHIR resource by type and id.

    Args:
        resource_type: FHIR resource type, e.g. "Patient" or "Condition".
        resource_id: server-assigned resource id, e.g. "mr-johnson-123".

    Returns:
        The resource as a JSON-decoded dict (the FHIR R4 representation).

    Example:
        >>> patient = get_resource("Patient", "mr-johnson-123")
        >>> patient["resourceType"]
        'Patient'
        >>> patient["name"][0]["family"]
        'Johnson'
    """
    url = f"{_base_url()}/{resource_type}/{resource_id}"
    response = requests.get(url, headers=_FHIR_JSON_HEADERS, timeout=_DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def search(resource_type: str, params: dict[str, str]) -> dict[str, Any]:
    """Run a FHIR search against the given resource type.

    Args:
        resource_type: FHIR resource type to search, e.g. "Condition".
        params: query parameters per the FHIR search spec, e.g.
            `{"subject": "Patient/mr-johnson-123"}`.

    Returns:
        A FHIR Bundle dict whose `entry` array contains the matching
        resources.

    Example:
        >>> bundle = search("Condition", {"subject": "Patient/mr-johnson-123"})
        >>> bundle["resourceType"]
        'Bundle'
        >>> len(bundle["entry"])
        1
    """
    url = f"{_base_url()}/{resource_type}"
    response = requests.get(
        url, headers=_FHIR_JSON_HEADERS, params=params, timeout=_DEFAULT_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response.json()


def get_patient_bundle(patient_id: str) -> dict[str, Any]:
    """Return the patient's full clinical chart as a single FHIR Bundle.

    Attempts the FHIR `Patient/$everything` operation first, which returns
    the patient plus their related clinical resources in one round-trip.
    Falls back to per-type searches (Patient, Condition, MedicationRequest,
    Encounter, Observation) if the server does not support `$everything`.

    Args:
        patient_id: FHIR Patient id, e.g. "mr-johnson-123".

    Returns:
        A FHIR `Bundle` dict (`resourceType: "Bundle"`) whose `entry` list
        wraps each clinical resource under an `entry[i].resource` key.

    Example:
        >>> bundle = get_patient_bundle("mr-johnson-123")
        >>> bundle["resourceType"]
        'Bundle'
        >>> {entry["resource"]["resourceType"] for entry in bundle["entry"]}
        {'Patient', 'Condition', 'MedicationRequest', 'Encounter', 'Observation'}
    """
    everything_url = f"{_base_url()}/Patient/{patient_id}/$everything"
    try:
        everything_response = requests.get(
            everything_url, headers=_FHIR_JSON_HEADERS, timeout=_EVERYTHING_TIMEOUT_SECONDS
        )
        if everything_response.ok:
            return everything_response.json()
    except requests.RequestException:
        # Fall through to the per-type-search fallback below.
        pass

    from mcp_server.constants import CHART_RESOURCE_TYPES

    bundle_entries: list[dict[str, Any]] = [
        {"resource": get_resource("Patient", patient_id)}
    ]
    for chart_resource_type in CHART_RESOURCE_TYPES:
        search_bundle = search(chart_resource_type, {"subject": f"Patient/{patient_id}"})
        for entry in search_bundle.get("entry", []) or []:
            bundle_entries.append({"resource": entry.get("resource", {})})
    return {"resourceType": "Bundle", "type": "searchset", "entry": bundle_entries}
