# PIPELINE.md — Agent Flow & Temporal Diagram

The full agent loop, end-to-end, for the deterministic demo scenario.

---

## High-Level Architecture

See `ARCHITECTURE.md` for the full stacked diagram. Three layers:

1. **Prompt Opinion UI** — provides chat, auth, SHARP context propagation
2. **A2A Orchestrator Agent** — runs the reasoning loop, chooses tools
3. **MCP Server (5 tools)** — talks to FHIR + mock payer

Two external services:
- **HAPI public FHIR server** — our EHR (synthetic patient data)
- **Local FastAPI mock payer** — fake insurance company

---

## The Temporal Flow (one complete PA case)

```
═══════════════════════════════════════════════════════════════════════════════
                         TEMPORAL FLOW — ONE PA CASE
═══════════════════════════════════════════════════════════════════════════════

   t=0   User: "Order MRI lumbar spine for patient mr-johnson-123"
                                  │
                                  ▼
         ┌──────── Orchestrator Agent receives request ────────┐
         │ Initial state:                                       │
         │   patient_id = "mr-johnson-123"                      │
         │   cpt_code = "72148"                                 │
         │   stage = "start"                                    │
         └──────────────────────────────────────────────────────┘
                                  │
   t=1   ┌────────── LOOP ITERATION 1 ──────────┐
         │  Thought: "Need to check if PA is    │
         │           required for CPT 72148"    │
         │  Action:  crd_check_coverage(        │
         │             cpt_code="72148",        │
         │             patient_id=...)          │
         │  Result:  { pa_required: true,       │
         │            questionnaire_id:         │
         │            "q-mri-lumbar-v1",        │
         │            payer_name:               │
         │            "MockHealth Plan" }       │
         │  State.stage = "pa_required"         │
         └──────────────────────────────────────┘
                                  │
   t=2   ┌────────── LOOP ITERATION 2 ──────────┐
         │  Thought: "Fetch the questionnaire"  │
         │  Action:  dtr_fetch_questionnaire(   │
         │             "q-mri-lumbar-v1")       │
         │  Result:  FHIR Questionnaire with    │
         │           4 items:                   │
         │           - pain-duration            │
         │           - conservative-therapy     │
         │           - red-flags                │
         │           - prior-imaging            │
         │  State.questionnaire = result        │
         └──────────────────────────────────────┘
                                  │
   t=3   ┌────────── LOOP ITERATION 3 ──────────┐
         │  Thought: "Read chart, draft answers │
         │           and clinical justification"│
         │  Action:  synthesize_clinical_       │
         │           justification(             │
         │             patient_id,              │
         │             cpt_code,                │
         │             questionnaire)           │
         │  ★ Fetches FHIR Bundle from HAPI     │
         │  ★ LLM reads Patient, Condition,     │
         │     MedicationRequests, Encounter,   │
         │     Observation                      │
         │  ★ Writes narrative + cites          │
         │     specific Resource/{id}s          │
         │  Result:  { answers, narrative,      │
         │            evidence_refs:[           │
         │            "Encounter/enc-pt-456",   │
         │            "MedicationRequest/...",  │
         │            ... ] }                   │
         └──────────────────────────────────────┘
                                  │
   t=4   ┌────────── LOOP ITERATION 4 ──────────┐
         │  Thought: "Submit the PA"            │
         │  Action:  pas_submit_bundle(         │
         │             patient_id,              │
         │             cpt_code,                │
         │             questionnaire_response,  │
         │             narrative,               │
         │             evidence_refs)           │
         │  Result:  { status: "denied",        │
         │            denial_reason:            │
         │            "Insufficient             │
         │             documentation of         │
         │             conservative therapy" }  │
         │  State.stage = "denied_first_pass"   │
         └──────────────────────────────────────┘
                                  │
   t=5   ┌────────── LOOP ITERATION 5 ──────────┐
         │  Thought: "Denial reason is wrong —  │
         │           the chart has the evidence.│
         │           Generate an appeal."       │
         │  Action:  appeal_denial(             │
         │             patient_id,              │
         │             denial_reason,           │
         │             original_narrative)      │
         │  ★ LLM re-reads chart                │
         │  ★ Identifies specific evidence the  │
         │     payer claimed was missing        │
         │  ★ Drafts formal appeal letter       │
         │  Result:  { appeal_letter,           │
         │            additional_evidence_refs} │
         └──────────────────────────────────────┘
                                  │
   t=6   ┌────────── LOOP ITERATION 6 ──────────┐
         │  Thought: "Resubmit with appeal"     │
         │  Action:  pas_submit_bundle(         │
         │             patient_id,              │
         │             cpt_code,                │
         │             questionnaire_response,  │
         │             narrative=appeal_letter, │
         │             evidence_refs=combined)  │
         │  Result:  { status: "approved",      │
         │            auth_number:              │
         │            "MH-AUTH-4F2A" }          │
         │  State.stage = "approved"            │
         └──────────────────────────────────────┘
                                  │
   t=7   Orchestrator → User:
         "✓ MRI lumbar spine approved.
          Authorization # MH-AUTH-4F2A.
          Note: Initial denial overturned via
          automated appeal citing prior failed
          conservative therapy."
```

---

## Why This is the "AI Factor"

A rules-based system would say "always run step 1 → 2 → 3 → 4". Our agent
says "what should I do *next* given what just happened?" — which is what
lets it gracefully handle the denial branch by deciding to appeal instead of
giving up.

Two specific tools require GenAI (no rule-based fallback exists):

- **`synthesize_clinical_justification`**: every payer's questionnaire is
  different, every patient's chart is structured differently in FHIR. Writing
  a narrative that cites specific resource IDs and maps to specific question
  fields requires reading comprehension + clinical reasoning + structured
  generation. Not solvable with rules.

- **`appeal_denial`**: the denial reason is unstructured text. Finding the
  specific FHIR evidence that rebuts that specific reason requires natural
  language understanding + chart navigation + persuasive writing.

The other 3 tools (CRD, DTR, PAS submit) are plumbing — they don't need GenAI.
The agent loop is what coordinates them all.

---

## Failure Modes & Recovery

For the demo, we use a deterministic happy path. In production,
the same loop would handle:

| Failure | Loop Response |
|---|---|
| CRD returns "PA not required" | Skip to ordering, no PA workflow |
| DTR returns 404 | Retry, then surface error to clinician |
| Synthesize tool returns insufficient evidence | Loop back, ask clinician for additional notes |
| PAS approval first try | Skip appeal step, return auth number |
| Appeal also denied | Surface to clinician for peer-to-peer review |

The agent's reasoning handles branching naturally — no hardcoded if/else.
