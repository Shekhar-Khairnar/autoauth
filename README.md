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

1. **CRD** — checks whether prior authorization is required and identifies
   the payer's questionnaire id.
2. **DTR** — fetches the structured FHIR Questionnaire to answer.
3. **Synthesize (GenAI)** — reads the patient's full FHIR chart and writes
   a cited medical-necessity narrative.
4. **PAS** — submits the prior-auth bundle for adjudication.
5. **Appeal (GenAI)** — when the first submission is denied, drafts a
   formal rebuttal letter citing the chart evidence the payer missed, then
   automatically resubmits and returns the final authorization number — all
   in a single tool call.

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
│ Payer responses    │               │ HAPI Public FHIR     │
│ in-process for the │               │ Synthetic patient    │
│ hosted MCP server; │               │ Mr. Johnson, 58M     │
│ optional FastAPI   │               │                      │
│ mock for local dev │               │                      │
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

## Try the Agent

Once the MCP server is registered in Prompt Opinion (or any MCP-compatible
orchestrator), send this single prompt to kick off the full workflow:

> **Order MRI lumbar spine for patient mr-johnson-123**

The agent will then:

1. **Check coverage requirements (CRD)** — confirms prior authorization is
   required and identifies the payer's questionnaire.
2. **Fetch the questionnaire (DTR)** — pulls the structured FHIR
   Questionnaire the payer wants answered.
3. **Synthesize clinical justification (GenAI)** — reads the patient's
   FHIR chart and drafts a medical-necessity narrative with explicit
   citations to specific FHIR resources.
4. **Submit prior authorization (PAS)** — sends the bundle for
   adjudication.
5. **Handle denials with an automated appeal (GenAI)** — when the first
   submission is denied, drafts a rebuttal citing the chart evidence the
   payer missed and resubmits, returning the final authorization number.

All clinical data is synthetic, hosted on the public HAPI FHIR R4 test
server at `https://hapi.fhir.org/baseR4`. No real patient information is
involved.

---

## Quickstart

The cloud-hosted MCP server uses in-process payer responses, so the only
moving parts you need to run are the MCP server itself and an ngrok
tunnel (if exposing to a hosted orchestrator).

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# edit .env to add your OPENROUTER_API_KEY

# 3. Seed the synthetic patient + chart to the public HAPI FHIR server
./scripts/seed.sh

# 4. Start the MCP server
./scripts/run_mcp_server.sh

# 5. (Hosted use) Expose port 8000 via ngrok
./scripts/ngrok.sh

# 6. Register the ngrok URL as an MCP server in your orchestrator
#    (e.g. Prompt Opinion), paste agent/orchestrator_system.md as the
#    agent's system prompt, then chat:
#    "Order MRI lumbar spine for patient mr-johnson-123"
```

### Optional: run the local mock payer

A FastAPI mock payer (`mock_payer/main.py`) is still bundled for local
end-to-end testing of the original HTTP-based PA workflow. Start it with
`./scripts/run_mock_payer.sh` if you want to exercise that path. The
cloud-deployed tools do not depend on it.

---

## Tech Stack

- **Python 3.11+**
- **MCP SDK** (`mcp[cli]`) — tool server protocol, streamable HTTP transport
- **OpenRouter** — LLM access (default model: Claude Haiku 4.5)
- **HAPI FHIR public test server** — synthetic patient EHR (R4)
- **Plain `requests`** — FHIR client (no FHIR SDK on purpose)
- **FastAPI + Uvicorn** — bundled mock payer for local end-to-end testing
- **ngrok** — exposes the local MCP server to a hosted orchestrator

---
