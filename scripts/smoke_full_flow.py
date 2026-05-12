"""End-to-end smoke test for AutoAuth.

Exercises the full prior-authorization pipeline without Prompt Opinion or
any A2A layer in between:

    CRD -> DTR -> synthesize -> PAS (denied) -> appeal -> PAS (approved)

Useful both as a CI-style regression check and as a plan-B demo when the
hosted UI is uncooperative.

Prereqs:
  - Mock payer running on http://localhost:8081 (see scripts/run_mock_payer.sh).
  - seed_fhir.seed_patient has been run against the configured FHIR server.
  - .env (or .env.example) supplies OPENROUTER_API_KEY.

Run from the project root: `python scripts/smoke_full_flow.py`.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import requests
from dotenv import load_dotenv

load_dotenv(".env") or load_dotenv(".env.example")

from mcp_server import constants
from mcp_server.tools import appeal, crd, dtr, pas, synthesize

_PAYER_RESET_URL = "http://localhost:8081/admin/reset"
_HR_WIDTH = 72


def print_step_header(label: str) -> None:
    """Print a banner separating one pipeline step from the next.

    Args:
        label: Short label describing the step, e.g. "1) CRD".

    Returns:
        None.

    Example:
        >>> print_step_header("1) CRD")
        ========================================================================
          1) CRD
        ========================================================================
    """
    print("\n" + "=" * _HR_WIDTH + f"\n  {label}\n" + "=" * _HR_WIDTH)


def main() -> None:
    """Drive the full happy-path PA flow end-to-end.

    Resets the mock payer's submission state, then runs each of the six
    pipeline steps in order. Asserts each branch (PA required, first denial,
    second approval) so a regression in any single tool fails the script.

    Returns:
        None. Prints each step's markdown summary and the final auth number.

    Example:
        $ python scripts/smoke_full_flow.py
        ...
        DONE - full PA flow succeeded end-to-end
        Authorization number: MH-AUTH-XXXXXXXX
    """
    # Force a fresh deny -> approve sequence regardless of prior demo runs.
    requests.post(_PAYER_RESET_URL, timeout=5)

    print_step_header("1) CRD - coverage discovery")
    coverage_decision = crd.run(constants.CPT_MRI_LUMBAR, constants.PATIENT_ID)
    print(coverage_decision["summary"])
    assert coverage_decision["pa_required"] is True, (
        "expected PA to be required for 72148"
    )

    print_step_header("2) DTR - fetch questionnaire")
    questionnaire_result = dtr.run(coverage_decision["questionnaire_id"])
    print(questionnaire_result["summary"])

    print_step_header("3) SYNTHESIZE (LLM) - draft justification")
    clinical_justification = synthesize.run(
        constants.PATIENT_ID,
        constants.CPT_MRI_LUMBAR,
        questionnaire_result["questionnaire"],
    )
    print(clinical_justification["summary"])

    print_step_header("4) PAS - first submission (expect DENIED)")
    initial_pas_decision = pas.run(
        constants.PATIENT_ID,
        constants.CPT_MRI_LUMBAR,
        clinical_justification["answers"],
        clinical_justification["narrative"],
        clinical_justification["evidence_refs"],
    )
    print(initial_pas_decision["summary"])
    assert initial_pas_decision["status"] == "denied", (
        f"expected denied, got {initial_pas_decision['status']}"
    )

    print_step_header("5) APPEAL (LLM) - draft appeal letter")
    appeal_packet = appeal.run(
        constants.PATIENT_ID,
        initial_pas_decision["denial_reason"],
        clinical_justification["narrative"],
    )
    print(appeal_packet["summary"])

    print_step_header("6) PAS - resubmit with appeal (expect APPROVED)")
    combined_evidence_refs = list(
        dict.fromkeys(
            clinical_justification["evidence_refs"]
            + appeal_packet["additional_evidence_refs"]
        )
    )
    final_pas_decision = pas.run(
        constants.PATIENT_ID,
        constants.CPT_MRI_LUMBAR,
        clinical_justification["answers"],
        appeal_packet["appeal_letter"],
        combined_evidence_refs,
    )
    print(final_pas_decision["summary"])
    assert final_pas_decision["status"] == "approved", (
        f"expected approved, got {final_pas_decision['status']}"
    )

    print_step_header("DONE - full PA flow succeeded end-to-end")
    print(f"Authorization number: {final_pas_decision['auth_number']}")


if __name__ == "__main__":
    main()
