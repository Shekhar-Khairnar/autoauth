# Prompt Opinion Setup — click-by-click

This is the manual config needed before the live demo. Roughly 5 minutes
once you have the four background services running.

## Prereqs (running in 4 terminals)

```powershell
# Terminal 1 - mock payer
.\.venv\Scripts\Activate.ps1
uvicorn mock_payer.main:app --port 8081 --reload

# Terminal 2 - MCP server (the toolbox the agent will call)
.\.venv\Scripts\Activate.ps1
python -m mcp_server.server

# Terminal 3 - ngrok tunnel so Prompt Opinion can reach :8000
ngrok http 8000
# Copy the https://...ngrok-free.app URL from ngrok's banner.

# (Terminal 4 is reserved for ad-hoc curl / re-seeding / etc.)
```

If you have not seeded the FHIR chart yet, do it once:

```powershell
.\.venv\Scripts\Activate.ps1
python -m seed_fhir.seed_patient
```

## Prompt Opinion side

1. Sign in to your Prompt Opinion workspace.
2. Open **MCP Servers** (or **Tools** / **Integrations** depending on UI
   version). Click **Add MCP Server**.
3. Fill in:
   - **Name:** `autoauth`
   - **Transport:** Streamable HTTP
   - **URL:** the ngrok https URL from Terminal 3, with `/mcp` appended if
     the platform requires an explicit MCP path. (FastMCP serves the
     streamable-http endpoint at `/mcp` by default.)
   - **Auth:** none (the demo has no auth layer)
4. Save. The UI should list 5 tools: `crd_check_coverage`,
   `dtr_fetch_questionnaire`, `synthesize_clinical_justification`,
   `pas_submit_bundle`, `appeal_denial`. If you see fewer, the server
   probably is not reachable — recheck the ngrok URL and that the MCP
   server terminal is alive.
5. Open **Agents** (or **Assistants**). Click **Create Agent**.
6. Fill in:
   - **Name:** `AutoAuth Orchestrator`
   - **Tagline:** "AI agents that win the prior authorization fight."
   - **Model:** the strongest model available on the platform.
   - **System prompt:** paste the entire contents of
     [orchestrator_system.md](orchestrator_system.md).
   - **Tools / MCP servers:** check the `autoauth` server you
     just added so all 5 tools are wired.
7. Save. Optional: publish to the marketplace if you need a public listing.

## Smoke test inside Prompt Opinion

In the agent's chat window, send:

> Order MRI lumbar spine (CPT 72148) for patient mr-johnson-123.

Expected behavior:

1. The agent calls `crd_check_coverage` — sees `pa_required=true`.
2. Calls `dtr_fetch_questionnaire` — receives the 4-item Questionnaire.
3. Calls `synthesize_clinical_justification` — generates the narrative
   with FHIR citations.
4. Calls `pas_submit_bundle` — receives `denied` with reason
   "Insufficient documentation of conservative therapy".
5. Calls `appeal_denial` — drafts the appeal letter.
6. Calls `pas_submit_bundle` a second time — receives `approved` with
   `auth_number`.
7. Replies to you with a markdown summary including the auth number and
   a note that the initial denial was overturned on appeal.

If you want to replay the demo, run this in Terminal 4 to reset the
mock payer's state:

```powershell
curl.exe -X POST http://localhost:8081/admin/reset
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Prompt Opinion says "no tools found" | ngrok URL wrong, MCP server crashed, or the platform expects `/mcp` suffix on the URL |
| `crd_check_coverage` errors with connection refused | mock payer (port 8081) not running |
| `synthesize_clinical_justification` returns auth error | `OPENROUTER_API_KEY` not set on the machine running the MCP server |
| Second `pas_submit_bundle` also returns denied | mock payer was restarted between calls — its state dict is in-memory |
| Agent calls `appeal_denial` before `pas_submit_bundle` | orchestrator system prompt was not pasted in full; re-paste it |

## A note on the "A2A" claim

The MCP server in this repo is your code. The orchestrator agent itself
runs inside Prompt Opinion's platform, which is what gives it A2A
exposure. You do not write A2A protocol code — Prompt Opinion's runtime
handles that when you create the agent. If a judge asks "where is the
A2A code", the honest answer is: the A2A layer is provided by Prompt
Opinion's platform; our work is the MCP toolbox plus the orchestrator
configuration in [orchestrator_system.md](orchestrator_system.md).
