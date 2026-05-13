"""Tool 2 of 5: Documentation Templates and Rules (Da Vinci DTR).

For the hosted-demo deployment the MCP server runs without a separately
deployed mock payer, so this tool returns a hardcoded FHIR Questionnaire
rather than HTTP-calling a payer service.
"""
from typing import Any

_HARDCODED_QUESTIONNAIRE: dict[str, Any] = {
    "resourceType": "Questionnaire",
    "id": "q-mri-lumbar-v1",
    "status": "active",
    "item": [
        {
            "linkId": "pain-duration",
            "text": "How long has the patient had low back pain?",
            "type": "string",
        },
        {
            "linkId": "conservative-therapy",
            "text": "Has the patient completed conservative therapy (PT/NSAIDs)?",
            "type": "boolean",
        },
        {
            "linkId": "red-flags",
            "text": "Any red flag symptoms (fever, unexplained weight loss)?",
            "type": "boolean",
        },
        {
            "linkId": "prior-imaging",
            "text": "Any prior lumbar imaging in the last 12 months?",
            "type": "boolean",
        },
    ],
}


def run(questionnaire_id: str, context: dict | None = None) -> dict[str, Any]:
    """Return the hardcoded MRI lumbar Questionnaire and a chat-ready summary.

    Args:
        questionnaire_id: Identifier returned by `crd_check_coverage`. Only
            "q-mri-lumbar-v1" is supported by this demo build; any other id
            still returns the same Questionnaire for hosted-deploy robustness.
        context: SHARP passthrough dict from Prompt Opinion carrying
            `patient_id`, `fhir_token`, and `practitioner_id`. Accepted on
            every tool so authentication propagation can be turned on
            without changing tool signatures.

    Returns:
        dict with keys:
            - questionnaire: the FHIR R4 Questionnaire resource dict.
            - summary: markdown block listing each `linkId`, `type`, `text`.

    Example:
        >>> result = run("q-mri-lumbar-v1")
        >>> result["questionnaire"]["resourceType"]
        'Questionnaire'
        >>> len(result["questionnaire"]["item"])
        4
    """
    questionnaire = _HARDCODED_QUESTIONNAIRE
    items = questionnaire["item"]
    item_bullets = [
        f"- `{item['linkId']}` ({item['type']}): {item['text']}"
        for item in items
    ]
    chat_summary = (
        f"## DTR Questionnaire `{questionnaire['id']}`\n\n"
        f"**Items to answer ({len(items)}):**\n" + "\n".join(item_bullets)
    )
    return {"questionnaire": questionnaire, "summary": chat_summary}
