# AutoAuth

**AI agents that win the prior authorization fight.**

A multi-agent healthcare system that automates US prior authorization using the
HL7 Da Vinci Burden Reduction implementation guides (CRD + DTR + PAS), with a
GenAI appeal agent that fights back against payer AI denials.

---

## The Problem

Prior authorization is the **#1 driver of US physician burnout in 2026**. The
numbers in 2026 are staggering:

- **90% of practices** saw PA requirements increase in the past year (MGMA 2026)
- **52.8 million** PA determinations in Medicare Advantage in 2024
- **4.1 million** denials, many of them overturned on appeal
- **82% overturn rate** when providers fight AI denials with provider-side AI
- **CMS-0057-F**, effective January 1, 2026, mandates FHIR-based electronic PA

The federal infrastructure exists. The agents don't.

---

## The Solution

An A2A orchestrator agent coordinates five MCP tools across the full PA
pipeline. When a clinician orders an MRI, the agent:

1. Checks coverage requirements via Da Vinci CRD
2. Fetches the payer's questionnaire via DTR
3. Reads the patient's full FHIR chart and writes a cited clinical
   justification using GenAI
4. Submits via PAS
5. When (not if) the payer's AI denies the claim, the agent re-reads the
   chart, identifies the rebutting evidence, and files a formal appeal
6. Returns the approval to the clinician — all in under a minute

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│            PROMPT OPINION PLATFORM (UI + SHARP)             │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  A2A AGENT: "PriorAuth Orchestrator"                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │   Agent reasoning loop:                             │    │
│  │   plan → pick tool → call → observe → repeat        │    │
│  └─────────────────────────────────────────────────────┘    │
└─┬───────────┬──────────────┬──────────────┬──────────┬──────┘
  │           │              │              │          │
  ▼           ▼              ▼              ▼          ▼
┌──────────────────────────────────────────────────────────┐
│ MCP SERVER: "Burden Reduction Toolkit"                   │
│ • crd_check_coverage                                     │
│ • dtr_fetch_questionnaire                                │
│ • synthesize_clinical_justification     ★ GenAI ★        │
│ • pas_submit_bundle                                      │
│ • appeal_denial                         ★ GenAI ★        │
└─────────┬──────────────────────────────────────┬─────────┘
          ▼                                      ▼
┌────────────────────┐               ┌──────────────────────┐
│ Mock Payer (PoC)   │               │ HAPI Public FHIR     │
│ FastAPI            │               │ Synthetic patient    │
│ /crd /dtr /pas     │               │ Mr. Johnson, 58M     │
└────────────────────┘               └──────────────────────┘
```

---

## How GenAI is Essential (the "AI Factor")

Two of our five tools require GenAI by definition; rules engines have failed
at these tasks for thirty years:

**`synthesize_clinical_justification`** reads heterogeneous FHIR data and
writes a payer-specific medical-necessity narrative with citations to specific
resource IDs. Every payer's questionnaire is different. Every patient's
chart is different. Every clinical justification needs to map the patient's
specific journey to the specific questions on the form. This is a reading
comprehension + clinical reasoning + structured writing task — not solvable
with rules.

**`appeal_denial`** parses an unstructured denial reason, identifies what
specific evidence in the chart rebuts that reason, and drafts a formal appeal
letter. Both the denial and the appeal are natural language. The matching
between denial claim and chart evidence requires NLU + chart navigation +
persuasive writing.

The three plumbing tools (CRD, DTR, PAS) don't need GenAI — but the agent
loop that decides when to call each one, and how to recover from a denial,
is itself a reasoning task that only an LLM agent handles gracefully.

---

## Standards-Compliant by Design

Every architectural choice maps to a published standard:

- **FHIR R4** — all clinical data lives as standard FHIR resources
- **US Core profiles** — Patient, Condition, MedicationRequest, Encounter,
  Observation conform to US Core 6.1+
- **Da Vinci Burden Reduction IGs** — CRD, DTR, PAS implemented per the
  HL7 specifications
- **CMS-0057-F** — the federal rule effective January 1, 2026 that mandates
  this exact workflow for Medicare Advantage, Medicaid, and ACA plans
- **SMART-on-FHIR scopes** — auth tokens scoped to `patient/*.read` and
  `patient/*.write` as needed, propagated through SHARP context

---

## Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# edit .env to add your OPENROUTER_API_KEY

# 3. Seed synthetic patient to HAPI public FHIR server
./scripts/seed.sh

# 4. Start the mock payer (terminal 1)
./scripts/run_mock_payer.sh

# 5. Start the MCP server (terminal 2)
./scripts/run_mcp_server.sh

# 6. Expose via ngrok for Prompt Opinion (terminal 3)
./scripts/ngrok.sh

# 7. Register the ngrok URL as an MCP server in Prompt Opinion
# 8. Configure A2A agent in Prompt Opinion UI to use the tools
# 9. Chat: "Order MRI lumbar spine for patient mr-johnson-123"
```

---

## Tech Stack

- **Python 3.11+**
- **MCP SDK** (`mcp[cli]`) — tool server protocol
- **OpenRouter** — LLM access (Claude Haiku)
- **FastAPI + Uvicorn** — mock payer endpoints
- **HAPI FHIR public test server** — synthetic patient EHR
- **Plain `requests`** — FHIR client
- **ngrok** — local-to-public tunnel during dev
- **Render** — final deployment for judging window

---
