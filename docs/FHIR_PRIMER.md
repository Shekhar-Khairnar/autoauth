# FHIR Primer (for data scientists)

The healthcare world is full of acronyms. This page exists so you can
understand every term in `ARCHITECTURE.md` without leaving the repo.

---

## FHIR — the universal medical data format

**Full form:** Fast Healthcare Interoperability Resources. Pronounced "fire."

**What it is:** A standardized JSON schema for medical data. Before FHIR, every
hospital's software stored patient data differently. FHIR said: a patient is a
`Patient` resource with these fields. A diagnosis is a `Condition` resource. A
prescription is a `MedicationRequest`. A lab result is an `Observation`. A
visit is an `Encounter`.

**Mental model:** MongoDB-style documents with a fixed schema. JSON over HTTP.

**Concrete example — an MRI order in FHIR:**

```json
{
  "resourceType": "ServiceRequest",
  "id": "mri-order-456",
  "status": "active",
  "intent": "order",
  "code": {
    "coding": [{"system": "http://www.ama-assn.org/cpt", "code": "72148"}],
    "text": "MRI Lumbar Spine without contrast"
  },
  "subject": {"reference": "Patient/mr-johnson-123"},
  "requester": {"reference": "Practitioner/dr-sarah-789"}
}
```

A patient's whole chart is a `Bundle` of dozens of these resources stitched together.

---

## FHIR server — the database holding all those resources

Just a REST API serving FHIR resources. Standard endpoints:

- `GET /Patient/123` → returns Patient 123
- `GET /Condition?patient=123` → all diagnoses for patient 123
- `GET /MedicationRequest?patient=123` → all prescriptions
- `GET /Patient/123/$everything` → all resources linked to patient 123
- `POST /ServiceRequest` → creates a new order
- `PUT /Patient/123` → upserts patient 123 (we use this in the seed script)

**HAPI FHIR** is the most popular open-source FHIR server — the "Postgres of FHIR".
We use the public test instance at `https://hapi.fhir.org/baseR4`. No auth,
read/write enabled, convenient for demos and integration testing.

---

## Da Vinci — the project that defined PA protocols

Not a technology. A name. The HL7 Da Vinci Project is a working group
(payers + providers + EHR vendors) that publishes "Implementation Guides" (IGs)
saying "here's how to use FHIR for specific business workflows."

Da Vinci published a bundle of three IGs collectively called **Burden Reduction**
— meaning "reduce the paperwork burden of prior authorization." Those three
IGs are **CRD, DTR, and PAS**, used in sequence.

---

## The Burden Reduction Pipeline (CRD → DTR → PAS)

### CRD — "Is PA even needed?"
**Full form:** Coverage Requirements Discovery.

Doctor is about to order an MRI. Their EHR pings the insurance company:
"For this patient with this plan, does CPT 72148 require prior auth, or can I
just order it?" The insurer answers yes/no, and if yes, returns a URL pointing
to the form they want filled out.

**Why this exists:** Today doctors waste time submitting PA for things that
didn't need it, or skipping PA on things that did. CRD removes the guesswork.

### DTR — "Give me the form to fill out"
**Full form:** Documentation Templates and Rules.

CRD said PA is needed and pointed to a form. DTR is the protocol for fetching
and filling that form. The form arrives as a FHIR `Questionnaire` resource —
a structured list of questions with expected answer types. Some answers
auto-fill from the chart (patient age, weight). Others need clinician input.

**Why this exists:** Every insurer used to have its own PDF form, web portal,
field names. DTR makes the form itself a standard data structure.

### PAS — "Submit the PA request"
**Full form:** Prior Authorization Support.

Once the questionnaire is filled, PAS packages everything (the answered
questionnaire + supporting clinical evidence + the order) into one FHIR
`Bundle` and ships it to the payer. The payer responds with `approved`,
`denied`, or `pending` (and a reason if denied).

**Why this exists:** This is the actual "submit and decide" step. Old way =
faxing PDFs. New way = posting a structured FHIR bundle, getting a structured
response.

---

## CMS-0057-F — the law that makes all this matter

**Full form:** CMS = Centers for Medicare & Medicaid Services. "0057-F" is the
filing number of the final rule.

**Effective:** January 1, 2026.

**What it requires:** Medicare Advantage, Medicaid, and ACA Marketplace
insurers must:
- Expose FHIR APIs supporting CRD/DTR/PAS
- Respond to urgent PA within 72 hours, standard within 7 days
- Give specific reasoning when they deny (no more black-box denials)
- Publicly report their denial rates

**Why our project hits this perfectly:** We're not solving a hypothetical
problem. We're building the provider-side piece for a workflow the federal
government just mandated. Judges (especially Microsoft's Josh Mandel,
co-creator of SMART on FHIR) will recognize this instantly.

---

## SMART on FHIR — the auth layer

**Full form:** Substitutable Medical Applications, Reusable Technologies on FHIR.

OAuth 2.0 tailored for healthcare. When your agent wants to read Mr. Johnson's
chart, it needs an access token scoped to "this patient, these resource types,
read-only." SMART defines how that token is obtained and what scopes look like
(e.g., `patient/Condition.read`).

**We don't implement this ourselves.** Prompt Opinion's SHARP context
propagation handles it — they pass the FHIR token through every tool call
automatically. We just accept the context dict.

---

## SHARP — Prompt Opinion's plumbing

Their context-propagation specs, not an industry standard. SHARP passes
healthcare context (patient_id, fhir_token, practitioner_id) through
multi-agent and multi-tool calls.

**We don't implement SHARP — we just accept it.** Every MCP tool function
takes a `context` parameter; Prompt Opinion fills it in when calling.

---

## MCP and A2A — the AI agent protocols

**MCP — Model Context Protocol.** Anthropic's standard for "how an LLM agent
talks to external tools." Our MCP server publishes 5 functions that any
LLM agent can call.

**A2A — Agent-to-Agent.** Google's standard for "how AI agents talk to other
AI agents." Lets one agent delegate tasks to another.

**Our project uses both:**
- MCP server = the toolbox (5 functions, called by our agent)
- A2A agent = the brain (calls those MCP tools, also exposed so other agents can call it)

---

## Quick Reference Card

| Term | One-line role |
|---|---|
| FHIR | The JSON schema for all medical data |
| HAPI | Open-source FHIR server we use as our EHR |
| Da Vinci | Working group that wrote the PA protocols |
| CRD | "Hey insurer, is PA needed?" |
| DTR | "Send me the form to fill out" |
| PAS | "Here's the filled form, approve it" |
| CMS-0057-F | The 2026 law forcing insurers to support CRD/DTR/PAS |
| SMART on FHIR | Healthcare OAuth |
| SHARP | Prompt Opinion's context plumbing |
| MCP | How agents call tools (our toolbox) |
| A2A | How agents call other agents (our orchestrator) |

---

## One Mental Model That Ties It All Together

> **FHIR** is the data format. **HAPI** stores it. **Da Vinci** wrote rules
> saying "use FHIR to do prior authorization." Those rules are **CRD → DTR → PAS**,
> which run in sequence. **CMS-0057-F** made those rules legally required in
> 2026. **MCP** is how our agent calls tools. **A2A** is how our agent talks to
> other agents. **SHARP** is Prompt Opinion's tool for passing patient ID +
> auth token between everything. We're building the AI brain that drives the
> whole pipeline automatically.
