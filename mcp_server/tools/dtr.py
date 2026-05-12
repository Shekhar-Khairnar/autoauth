"""Tool 2 of 5: Documentation Templates and Rules (Da Vinci DTR).

Once CRD has confirmed PA is required and named a Questionnaire id, the DTR
step retrieves that structured Questionnaire from the payer. The
Questionnaire's `item[]` array tells the orchestrator exactly which fields
the medical-necessity narrative must answer.
"""
from typing import Any

from mcp_server import payer_client


def run(questionnaire_id: str, context: dict | None = None) -> dict[str, Any]:
    """Retrieve the payer's DTR Questionnaire and summarize its items.

    Calls the payer's `/dtr/questionnaire/{id}` endpoint and returns the raw
    FHIR R4 Questionnaire alongside a markdown summary listing each item so
    the chat surface can show the user which fields will be answered.

    Args:
        questionnaire_id: Identifier returned by `crd_check_coverage`,
            e.g. "q-mri-lumbar-v1".
        context: SHARP passthrough dict from Prompt Opinion carrying
            `patient_id`, `fhir_token`, and `practitioner_id`. Accepted on
            every tool so authentication propagation can be turned on
            without changing tool signatures.

    Returns:
        dict with keys:
            - questionnaire: dict, the FHIR R4 Questionnaire resource.
            - summary: str, markdown block enumerating each `item.linkId`,
              `item.type`, and `item.text`.

    Example:
        >>> result = run("q-mri-lumbar-v1")
        >>> result["questionnaire"]["resourceType"]
        'Questionnaire'
        >>> "pain-duration" in result["summary"]
        True
    """
    questionnaire = payer_client.dtr_call(questionnaire_id)
    items = questionnaire.get("item", []) or []
    item_bullets = [
        f"- `{item.get('linkId','?')}` ({item.get('type','string')}): {item.get('text','')}"
        for item in items
    ]
    chat_summary = (
        f"## DTR Questionnaire `{questionnaire.get('id', questionnaire_id)}`\n\n"
        f"**Title:** {questionnaire.get('title', '(untitled)')}\n\n"
        f"**Items to answer ({len(items)}):**\n" + "\n".join(item_bullets)
    )
    return {"questionnaire": questionnaire, "summary": chat_summary}
