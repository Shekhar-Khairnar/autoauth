# AutoAuth — Architecture

This file is the architectural source of truth for the project. Read it
before reviewing or extending the codebase. Every convention and
constraint listed here is load-bearing for the product and for the standards
compliance story (CMS-0057-F, Da Vinci CRD/DTR/PAS, US Core).

---

## Project Summary

AutoAuth is a multi-agent healthcare system that automates US prior
authorization (PA) using the HL7 Da Vinci Burden Reduction implementation guides
(CRD + DTR + PAS), with a GenAI appeal agent that fights back against payer AI
denials. It maps directly to CMS-0057-F, the federal interoperability and prior
authorization rule effective January 1, 2026.

---

## Glossary (insider acronyms, one line each)

| Term | Full form | Role |
|---|---|---|
| **FHIR** | Fast Healthcare Interoperability Resources | The JSON schema standard for medical data (Patient, Condition, MedicationRequest, Encounter, Observation, etc.) |
| **HAPI FHIR** | (HL7 API) | The most popular open-source FHIR server. We use the public test instance at `https://hapi.fhir.org/baseR4` |
| **Synthea** | (synthetic + EHR) | Tool that generates fake patient charts in FHIR. We don't need it; we seed our own resources |
| **Da Vinci** | (HL7 project name) | Standards working group that publishes the PA implementation guides |
| **CRD** | Coverage Requirements Discovery | Provider asks payer "is PA required for this order?" |
| **DTR** | Documentation Templates and Rules | Payer sends the structured Questionnaire form to fill out |
| **PAS** | Prior Authorization Support | Provider submits the completed PA bundle; payer approves/denies |
| **CMS-0057-F** | (federal rule number) | US rule effective Jan 1 2026 mandating FHIR-based PA for Medicare Advantage, Medicaid, ACA plans |
| **SMART on FHIR** | Substitutable Medical Apps, Reusable Technologies on FHIR | OAuth 2.0 profile for healthcare; defines token scopes like `patient/Condition.read` |
| **SHARP** | (Prompt Opinion's term) | Their context-propagation protocol for passing patient_id, fhir_token, practitioner_id through agent/tool calls |
| **MCP** | Model Context Protocol | Anthropic's standard for how LLM agents call external tools. Our tool server speaks MCP |
| **A2A** | Agent-to-Agent | Google's standard for how AI agents talk to other AI agents. Our orchestrator is A2A-compliant |

---

## Architecture (ASCII Pipeline)

```
═══════════════════════════════════════════════════════════════════════════════
                    AUTOAUTH — SYSTEM PIPELINE
═══════════════════════════════════════════════════════════════════════════════

   ┌─────────────────────────────────────────────────────────────────────┐
   │                    PROMPT OPINION PLATFORM (UI)                     │
   │                                                                     │
   │   Dr. Sarah: "Order MRI lumbar spine for patient mr-johnson-123"    │
   │                                                                     │
   └────────────────────────────────┬────────────────────────────────────┘
                                    │ SHARP context:
                                    │   { patient_id, fhir_token,
                                    │     practitioner_id }
                                    ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │             A2A AGENT: "PriorAuth Orchestrator"  (Path B)           │
   │                                                                     │
   │   ┌─────────────────────────────────────────────────────────────┐   │
   │   │              ⟲   AGENT REASONING LOOP   ⟲                   │   │
   │   │                                                             │   │
   │   │   while not done:                                           │   │
   │   │     thought  = LLM.plan(state, history)                     │   │
   │   │     action   = pick_tool(thought)                           │   │
   │   │     result   = call_mcp_tool(action)                        │   │
   │   │     state    = update(state, result)                        │   │
   │   │     if approved or final_appeal: done                       │   │
   │   └─────────────────────────────────────────────────────────────┘   │
   └─┬────────────┬─────────────┬───────────────┬──────────────┬────────┘
     │ tool 1     │ tool 2      │ tool 3        │ tool 4       │ tool 5
     ▼            ▼             ▼               ▼              ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │       MCP SERVER: "Burden Reduction Toolkit"   (Path A)          │
   │                                                                  │
   │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐  │
   │  │ crd_check_   │ │ dtr_fetch_   │ │ synthesize_clinical_     │  │
   │  │ coverage     │ │ questionnaire│ │ justification ★ GENAI ★  │  │
   │  └──────┬───────┘ └──────┬───────┘ └────────────┬─────────────┘  │
   │  ┌──────┴───────┐ ┌──────┴────────────┐         │                │
   │  │ pas_submit_  │ │ appeal_denial     │         │                │
   │  │ bundle       │ │      ★ GENAI ★    │         │                │
   │  └──────┬───────┘ └──────┬────────────┘         │                │
   └─────────┼────────────────┼──────────────────────┼────────────────┘
             ▼                ▼                      ▼
   ┌──────────────────────┐  ┌──────────────────────────────────────┐
   │  MOCK PAYER (8081)   │  │  FHIR SERVER (HAPI test, public)     │
   │  FastAPI             │  │  https://hapi.fhir.org/baseR4        │
   │                      │  │                                      │
   │  /crd/coverage-      │  │  Patient/mr-johnson-123              │
   │    discovery         │  │  ├─ Condition (low back pain)        │
   │  /dtr/questionnaire/ │  │  ├─ MedicationRequest (ibuprofen)    │
   │    {id}              │  │  ├─ MedicationRequest (gabapentin)   │
   │  /pas/claim          │  │  ├─ Encounter (PT, 8 sessions)       │
   │                      │  │  └─ Observation (no red flags)       │
   └──────────────────────┘  └──────────────────────────────────────┘
```

---

## The 5 MCP Tools — Full Specifications

Each tool accepts a `context` dict (Prompt Opinion's SHARP context:
`patient_id`, `fhir_token`, `practitioner_id`). The dict is currently
accepted for API compatibility; SHARP propagation is enabled at the
Prompt Opinion integration step rather than inside the tools.

### 1. `crd_check_coverage`
- **Input:** `cpt_code: str`, `patient_id: str`
- **Output:** `{ pa_required: bool, questionnaire_id: str | None, payer_name: str }`
- **Logic:** POST to mock payer `/crd/coverage-discovery`. Mock payer always
  returns `pa_required: true` for CPT 72148 (MRI lumbar spine).

### 2. `dtr_fetch_questionnaire`
- **Input:** `questionnaire_id: str`
- **Output:** A FHIR Questionnaire resource (dict) with 4 items:
  pain duration, conservative therapy tried, red flag symptoms, prior imaging
- **Logic:** GET to mock payer `/dtr/questionnaire/{id}`.

### 3. `synthesize_clinical_justification` ★ GENAI ★
- **Input:** `patient_id: str`, `cpt_code: str`, `questionnaire: dict`
- **Output:** `{ answers: dict, narrative: str, evidence_refs: list[str] }`
  - `answers`: maps question `linkId` → answer string
  - `narrative`: markdown medical-necessity justification
  - `evidence_refs`: FHIR refs like `"Encounter/enc-pt-456"` cited in narrative
- **Logic:** Fetch full patient bundle from HAPI. Pass to LLM with
  `prompts/synthesize_system.md`. Parse structured JSON output.

### 4. `pas_submit_bundle`
- **Input:** `patient_id: str`, `cpt_code: str`, `questionnaire_response: dict`,
  `narrative: str`, `evidence_refs: list[str]`
- **Output:** `{ status: "approved" | "denied" | "pending", auth_number: str | None, denial_reason: str | None }`
- **Logic:** POST to mock payer `/pas/claim`. Mock payer's deterministic
  behavior: first submission for a patient_id returns `denied` with reason
  "Insufficient documentation of conservative therapy". Second submission
  returns `approved` with fake auth number. Module-level dict tracks state.

### 5. `appeal_denial` ★ GENAI ★
- **Input:** `patient_id: str`, `denial_reason: str`, `original_narrative: str`
- **Output:** `{ appeal_letter: str, additional_evidence_refs: list[str] }`
- **Logic:** Re-fetch FHIR bundle, pass denial reason + original narrative to
  LLM with `prompts/appeal_system.md`. LLM identifies specific FHIR evidence
  that rebuts the denial reason. Returns formatted appeal letter.

---

## Demo Happy Path (the deterministic scenario)

- **Patient ID:** `mr-johnson-123`
- **CPT code:** `72148` (MRI lumbar spine without contrast)
- **Expected agent loop iterations:** 6
  1. `crd_check_coverage` → `pa_required: true`
  2. `dtr_fetch_questionnaire` → returns 4-item Questionnaire
  3. `synthesize_clinical_justification` → narrative + evidence refs
  4. `pas_submit_bundle` → `denied` with reason
  5. `appeal_denial` → appeal letter with additional evidence
  6. `pas_submit_bundle` → `approved` with auth number
- **Final orchestrator message:** "MRI approved. Authorization # MH-AUTH-XXXX."

---

## Environment Variables

```
OPENROUTER_API_KEY=
LLM_MODEL=anthropic/claude-haiku-4.5
FHIR_BASE_URL=https://hapi.fhir.org/baseR4
PAYER_BASE_URL=http://localhost:8081
MCP_PORT=8000
```

---

## How to Run Each Component

```bash
# 1. Mock payer (terminal 1)
./scripts/run_mock_payer.sh

# 2. Seed FHIR data (one-time, terminal 2)
./scripts/seed.sh

# 3. MCP server (terminal 2 or 3)
./scripts/run_mcp_server.sh

# 4. ngrok tunnel (terminal 4) — public URL for Prompt Opinion
./scripts/ngrok.sh
```

---

## Naming Conventions

- All filenames and functions: `snake_case`
- LLM prompts live in `mcp_server/prompts/*.md`, loaded at runtime
- All FHIR references in code MUST include resource type prefix:
  - GOOD: `"Encounter/enc-pt-456"`
  - BAD: `"enc-pt-456"`
- Tool function docstrings are READ BY THE AGENT LLM at call time — write them
  to make tool-selection decisions easy. Specify when to use, when NOT to use,
  example inputs, and what the output looks like.
- Hardcoded demo IDs are constants in `mcp_server/constants.py`

---

## Evaluation Criteria Alignment

The architecture is designed around three product and evaluation criteria:

### AI Factor — "leverages GenAI for what rules-based can't do"
- Tools: `synthesize_clinical_justification`, `appeal_denial`
- These tools READ heterogeneous FHIR data and WRITE clinical narratives. No
  rules engine can do this; every payer's questionnaire is different, every
  patient's chart is different, every denial reason needs different evidence.
- Rules-based fallbacks are intentionally avoided for these two tools because the LLM reasoning is the core capability.

### Potential Impact — "addresses a real pain point"
- Supporting evidence: MGMA 2026 (90% practices saw PA increase), 52.8M PA
  determinations in MA 2024, 4.1M denials (7.7% denial rate), 82% AI-overturn
  rate when providers appeal.
- Frame: prior auth is the #1 driver of US physician burnout in 2026.

### Feasibility — "could exist in real healthcare; respects regs"
- Maps to CMS-0057-F (effective Jan 1, 2026)
- Uses real Da Vinci Burden Reduction IGs (CRD/DTR/PAS)
- Uses real FHIR R4 resources via real HAPI server
- Synthetic data only — no PHI
- Auth via SMART-on-FHIR scopes (passed through SHARP context)

---

## Design Constraints

- Uses synthetic patient data only; no real PHI is included.
- Focuses on standards-native prior authorization workflows rather than faxing, PDF parsing, or payer portal scraping.
- Keeps clinical synthesis and appeal generation GenAI-driven rather than rules-based.
- Uses Prompt Opinion as the chat interface instead of a separate frontend.
- Uses lightweight HTTP clients with `requests` instead of a heavyweight FHIR SDK.
- Keeps the implementation scoped to the five MCP tools, mock payer, and FHIR seed workflow.
