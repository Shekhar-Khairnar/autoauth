"""Single-tool smoke test for synthesize_clinical_justification.

Exercises the GenAI synthesize tool in isolation against the seeded demo
patient (`mr-johnson-123`) using a hard-coded Questionnaire that mirrors
what the mock payer's DTR endpoint returns.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(".env") or load_dotenv(".env.example")

from mcp_server.tools.synthesize import run

DEMO_QUESTIONNAIRE = {
    "resourceType": "Questionnaire",
    "id": "q-mri-lumbar-v1",
    "status": "active",
    "item": [
        {"linkId": "pain-duration", "text": "Duration of low back pain (weeks).",
         "type": "integer"},
        {"linkId": "conservative-therapy",
         "text": "Completed >=6 weeks of conservative therapy?", "type": "boolean"},
        {"linkId": "red-flags", "text": "Red-flag symptoms present?", "type": "boolean"},
        {"linkId": "prior-imaging", "text": "Lumbar imaging in last 12 months?",
         "type": "boolean"},
    ],
}

if __name__ == "__main__":
    result = run("mr-johnson-123", "72148", DEMO_QUESTIONNAIRE)
    print(result["summary"])
    print("\nevidence_refs:", result["evidence_refs"])
