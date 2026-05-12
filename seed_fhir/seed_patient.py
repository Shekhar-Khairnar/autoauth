"""Seed deterministic AutoAuth demo resources into a FHIR server.

PUTs every resource in `seed_fhir/resources/` to the configured FHIR server
using a fixed id per resource. PUT-by-id leverages FHIR's "update as create"
semantics, so re-running the script is idempotent: old versions get
overwritten in place rather than producing duplicates.

Run from the project root: `python -m seed_fhir.seed_patient`.
"""
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

FHIR_BASE_URL = os.getenv("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4").rstrip("/")
RESOURCES_DIR = Path(__file__).parent / "resources"

# Insert order matters: Patient must exist before resources that reference it.
SEED_ORDER = [
    "patient.json",
    "condition_back_pain.json",
    "med_ibuprofen.json",
    "med_gabapentin.json",
    "encounter_pt.json",
    "observation_no_redflags.json",
]


def put_resource(resource: dict) -> str:
    """PUT a single FHIR resource to the configured FHIR server.

    Uses the resource's `resourceType` and `id` fields to build the URL,
    relying on FHIR's update-as-create semantics so the script is idempotent.

    Args:
        resource: A FHIR R4 resource dict with at least `resourceType` and
            `id` set.

    Returns:
        The full URL that was written to, e.g.
        `https://hapi.fhir.org/baseR4/Patient/mr-johnson-123`.

    Example:
        >>> put_resource({
        ...     "resourceType": "Patient",
        ...     "id": "mr-johnson-123",
        ...     "name": [{"family": "Johnson"}],
        ... })
        'https://hapi.fhir.org/baseR4/Patient/mr-johnson-123'
    """
    resource_type = resource["resourceType"]
    resource_id = resource["id"]
    target_url = f"{FHIR_BASE_URL}/{resource_type}/{resource_id}"
    response = requests.put(
        target_url,
        json=resource,
        headers={
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        },
        timeout=30,
    )
    response.raise_for_status()
    return target_url


def main() -> int:
    """Seed all demo resources in dependency order.

    Reads each JSON file listed in `SEED_ORDER`, PUTs it to the FHIR server,
    and prints a per-resource confirmation. Exits non-zero if any expected
    file is missing from `seed_fhir/resources/`.

    Returns:
        Process exit code: 0 on success, 1 if a resource file is missing.

    Example:
        >>> main()
        0
    """
    print(f"Seeding demo chart to {FHIR_BASE_URL}\n")
    seeded_urls: list[str] = []
    for resource_filename in SEED_ORDER:
        resource_path = RESOURCES_DIR / resource_filename
        if not resource_path.exists():
            print(f"  MISSING: {resource_path}", file=sys.stderr)
            return 1
        with resource_path.open() as resource_file:
            resource_body = json.load(resource_file)
        seeded_url = put_resource(resource_body)
        seeded_urls.append(seeded_url)
        print(f"  PUT  {resource_filename:36s} -> {seeded_url}")

    print("\nSeed complete. Demo patient: Patient/mr-johnson-123")
    print("Bundle ($everything):")
    print(f"  GET  {FHIR_BASE_URL}/Patient/mr-johnson-123/$everything")
    return 0


if __name__ == "__main__":
    sys.exit(main())
