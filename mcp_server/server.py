"""AutoAuth - AI agents for healthcare prior authorization.

Implements the HL7 Da Vinci Burden Reduction workflow (CRD/DTR/PAS) with
GenAI clinical justification and automated denial appeals.

Compliant with CMS-0057-F (Jan 1, 2026).

This module is the MCP server entry point. It registers the five
PriorAuth tools and serves them over streamable HTTP on port 8000 so the
orchestrating agent (hosted in Prompt Opinion) can reach them via ngrok.
The docstrings on the registered tool functions below are what the
orchestrator's LLM reads at tool-selection time -- keep them concrete.
"""
import os
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_server.tools import appeal, crd, dtr, pas, synthesize

load_dotenv()

mcp = FastMCP(
    "autoauth",
    host="0.0.0.0",
    port=int(os.getenv("MCP_PORT", "8000")),
)


@mcp.tool()
def crd_check_coverage(cpt_code: str, patient_id: str) -> dict[str, Any]:
    """Step 1 of the Da Vinci prior-authorization flow. Ask the payer's CRD
    (Coverage Requirements Discovery) endpoint whether prior authorization is
    required for the given CPT procedure code and patient, and if so which
    DTR questionnaire id to fetch next.

    Always call this FIRST. If pa_required is false, stop and inform the user
    that no PA is needed.

    Args:
        cpt_code: CPT/HCPCS procedure code (e.g. "72148" = MRI lumbar spine).
        patient_id: FHIR Patient id (e.g. "mr-johnson-123").

    Returns:
        dict with keys: pa_required (bool), questionnaire_id (str | None),
        payer_name (str), summary (markdown string for chat display).
    """
    return crd.run(cpt_code, patient_id)


@mcp.tool()
def dtr_fetch_questionnaire(questionnaire_id: str) -> dict[str, Any]:
    """Step 2 of the Da Vinci flow. Retrieve the FHIR Questionnaire the
    payer's DTR (Documentation Templates and Rules) endpoint says we must
    answer. Call this after crd_check_coverage returns pa_required=true.

    Args:
        questionnaire_id: id returned by crd_check_coverage.

    Returns:
        dict with keys: questionnaire (FHIR Questionnaire resource), summary
        (markdown listing each item's linkId, text and type).
    """
    return dtr.run(questionnaire_id)


@mcp.tool()
def synthesize_clinical_justification(
    patient_id: str,
    cpt_code: str,
    questionnaire: dict[str, Any],
) -> dict[str, Any]:
    """Step 3 - the headline GenAI tool. Pull the patient's full clinical
    bundle from FHIR (Conditions, prior MedicationRequests, Encounters,
    Observations) and use an LLM to (a) answer every Questionnaire item with
    explicit FHIR-grounded evidence and (b) draft a medical-necessity
    narrative citing specific resources.

    Call this after dtr_fetch_questionnaire. The outputs are direct inputs to
    pas_submit_bundle.

    Args:
        patient_id: FHIR Patient id whose chart to reason over.
        cpt_code: requested procedure code (for context inside the narrative).
        questionnaire: the FHIR Questionnaire returned by dtr_fetch_questionnaire.

    Returns:
        dict with keys: answers (linkId -> answer), narrative (markdown),
        evidence_refs (list of FHIR refs like "Encounter/enc-pt-456"),
        summary (markdown for chat display).
    """
    return synthesize.run(patient_id, cpt_code, questionnaire)


@mcp.tool()
def pas_submit_bundle(
    patient_id: str,
    cpt_code: str,
    questionnaire_response: dict[str, Any],
    narrative: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    """Step 4 - submit the completed PA bundle to the payer's PAS (Prior
    Authorization Support) endpoint and return their adjudication. If status
    is 'denied', the orchestrator should follow up with appeal_denial, then
    re-call pas_submit_bundle with the appeal letter as the narrative.

    Args:
        patient_id: FHIR Patient id.
        cpt_code: requested procedure code.
        questionnaire_response: linkId -> answer mapping from synthesize.
        narrative: medical-necessity narrative (or appeal letter on resubmit).
        evidence_refs: FHIR resource references cited as evidence.

    Returns:
        dict with keys: status ("approved" | "denied" | "pending"),
        auth_number (str | None), denial_reason (str | None), summary
        (markdown for chat display).
    """
    return pas.run(patient_id, cpt_code, questionnaire_response, narrative, evidence_refs)


@mcp.tool()
def appeal_denial(
    patient_id: str,
    denial_reason: str,
    original_narrative: str,
) -> dict[str, Any]:
    """Step 5 - the GenAI appeal agent. Re-read the FHIR chart, identify the
    specific evidence that rebuts the payer's stated denial reason, and draft
    a formal appeal letter. After this returns, the orchestrator should call
    pas_submit_bundle again with the appeal letter as the narrative.

    Args:
        patient_id: FHIR Patient id.
        denial_reason: the denial_reason string returned by pas_submit_bundle.
        original_narrative: narrative that was originally submitted.

    Returns:
        dict with keys: appeal_letter (markdown), additional_evidence_refs
        (list of FHIR refs), summary (markdown for chat display).
    """
    return appeal.run(patient_id, denial_reason, original_narrative)


def main() -> None:
    print(f"Starting autoauth MCP server on port {os.getenv('MCP_PORT', '8000')}")
    print("Transport: streamable-http")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
