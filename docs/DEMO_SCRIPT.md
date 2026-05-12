# DEMO_SCRIPT.md — 3-Minute Video Shot List

The product demo video should stay under 3 minutes and can be hosted on
YouTube as an unlisted video. This is the literal shot list.

**Total runtime target: 2:50** (gives buffer for slow uploads).

---

## 0:00 – 0:20 | The Problem

**On screen:** Full-bleed slide with these stats stacked vertically (one per beat):

- "**Prior authorization** — the #1 driver of US physician burnout in 2026"
- "**90%** of practices saw PA requirements increase in the past year (MGMA 2026)"
- "**52.8 million** PA determinations in Medicare Advantage, 2024"
- "**4.1 million** denials — many overturned on appeal"
- "**CMS-0057-F** went into effect January 1, 2026"

**Voiceover:**
> "In 2026, prior authorization is the number one driver of US physician
> burnout. Insurers made 52 million PA determinations last year and denied
> over 4 million. The federal government just mandated FHIR-based electronic
> prior auth through CMS-0057-F. The infrastructure exists. The agents don't."

---

## 0:20 – 0:45 | The Solution & Architecture

**On screen:** Architecture diagram (use the ASCII from PIPELINE.md, cleaned
up in Excalidraw or just rendered nicely). Label clearly:
- Prompt Opinion UI (top)
- A2A Orchestrator Agent (middle, with "Agent Loop" labeled)
- 5 MCP Tools (boxes labeled CRD / DTR / Synthesize / PAS / Appeal)
- HAPI FHIR + Mock Payer (bottom)
- Highlight the two ★ GENAI ★ tools in a different color

**Voiceover:**
> "AutoAuth is a multi-agent system built on the HL7 Da Vinci Burden
> Reduction implementation guides. An A2A orchestrator agent coordinates five
> MCP tools that handle the full PA pipeline: coverage discovery, documentation
> templates, clinical justification, submission, and — critically — automated
> appeals when payer AI denies. Two of those tools are pure GenAI; rules
> engines can't write clinical justifications or rebut unstructured denials."

---

## 0:45 – 2:00 | Live Demo Inside Prompt Opinion

**Setup before recording:**
- Browser at Prompt Opinion app, your A2A agent open in chat
- Mock payer running locally (terminal visible in second monitor or hidden)
- Seed FHIR data already loaded
- Test the full flow once before hitting record

**Shot list:**

**0:45** Type into Prompt Opinion chat (let viewer see typing):
> `Order MRI lumbar spine for patient mr-johnson-123`

Hit enter.

**0:50** Agent begins reasoning. On screen, the Prompt Opinion UI will show
each tool call expanding. Use cursor to point at:

- Tool call 1: `crd_check_coverage` → expand → show `pa_required: true`
- Tool call 2: `dtr_fetch_questionnaire` → show the 4-item Questionnaire
- Tool call 3: `synthesize_clinical_justification` → **PAUSE HERE**, expand
  fully, let viewer read the markdown justification with FHIR citations

**Voiceover during call 3:**
> "The synthesize tool reads the patient's full FHIR bundle — every
> condition, every prior medication trial, every encounter — and writes
> a clinical justification with citations to specific resource IDs. Eight
> sessions of physical therapy, two failed pharmacotherapy trials, no red
> flag symptoms. Every claim traceable to the chart."

**1:25** Continue:
- Tool call 4: `pas_submit_bundle` → expand → show `status: denied`,
  `denial_reason: "Insufficient documentation of conservative therapy"`
- On-screen text overlay: "**Payer AI denial — 82% of which are wrong**"

**1:35** Tool call 5: `appeal_denial` → **PAUSE HERE**, expand fully

**Voiceover:**
> "The agent recognizes the denial is wrong — the conservative therapy was
> documented. The appeal tool re-reads the chart, identifies the specific
> evidence the payer missed, and drafts a formal appeal letter."

**1:55** Tool call 6: `pas_submit_bundle` (second time) →
`status: approved`, `auth_number: MH-AUTH-XXXX`

---

## 2:00 – 2:45 | Why This Wins

**On screen:** Three stacked bullets, each appearing as you speak it.

**Voiceover:**
> "Three things make this compelling:

> **One — the AI Factor.** Writing payer-specific clinical justifications and
> rebutting unstructured denials are reasoning tasks. No rules engine has
> solved them in thirty years. LLMs reading FHIR bundles and writing cited
> narratives is the textbook case for GenAI in healthcare.

> **Two — the impact.** PA is the top burnout cause. It delays care, causes
> measurable patient harm, and costs the system billions. Even small wins
> here are huge.

> **Three — feasibility.** This isn't a hypothetical. The Da Vinci Burden
> Reduction guides — CRD, DTR, PAS — were mandated by CMS-0057-F as of
> January first, 2026. We use real FHIR, real US Core profiles, real HAPI
> servers. SMART-on-FHIR auth via SHARP context. This could deploy tomorrow."

---

## 2:45 – 3:00 | Outro

**On screen:** Prompt Opinion Marketplace listing of your project. Show:
- Project name: "AutoAuth"
- Tagline: "AI agents that win the prior authorization fight"
- Your username

**Voiceover (last 5 seconds):**
> "AutoAuth. Built on Prompt Opinion. Submitted to Agents Assemble 2026."

---

## Recording Tips

- Use **OBS Studio** (free, all platforms) or **QuickTime** (Mac built-in)
- Record at 1080p minimum, mp4 output
- Hide browser bookmarks bar, sidebars, notifications
- Close all other tabs except Prompt Opinion
- Bump your system font size up one notch before recording so judges on
  small screens can read tool outputs
- Record voiceover separately if your dev environment is noisy; sync after
- One take per section is fine — don't perfect; ship

---

## Final Checklist Before Uploading

- [ ] Total length under 3:00
- [ ] Audio is audible (not too quiet, no clipping)
- [ ] All stats on screen are readable
- [ ] FHIR resource IDs visible in justification output (key visual)
- [ ] Denial → appeal → approval sequence clearly visible
- [ ] No PHI anywhere on screen (only synthetic "Mr. Johnson")
- [ ] Upload to YouTube as **unlisted**, copy link
- [ ] Paste link into the submission or project page
