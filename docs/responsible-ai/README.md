# Responsible AI on Agent Engine: Agent Gateway, Model Armor & SCC

This is the write-up of an investigation into how **Agent Gateway**, **Model
Armor**, and **Security Command Center (SCC)** protect the two Agent Engine
deployments of this agent — the ADK deployment (`financial-advisor-adk`) and
the A2A deployment (`financial-advisor-a2a`) — and what does *not* currently
work. It started from one symptom ("the agent-details Security tab shows 0
violations") and turned into a full map of the request path, a red-team pass
with five adversarial prompts, and a list of concrete gaps to raise with
Google Cloud support.

**Scope:** project `gemini-agent-101`, region `us-central1`. Reasoning
Engines `financial-advisor-adk` (`4756172291677618176`) and
`financial-advisor-a2a` (`6099511618029223936`), ingress gateway
`financial-advisor-ingress-gw`, Model Armor template
`financial-advisor-security`. Last verified against live GCP state:
**2026-08-20**.

## Table of contents

1. [Controls overview](01-controls-overview.md) — what Agent Gateway, Model
   Armor (gateway template vs. floor settings), SCC, and Threat Detection
   each are, and how they're wired to this project today.
2. [Request → response flow](02-request-response-flow.md) — **mandatory
   diagrams**: the full journey of a prompt through GCP components for both
   the ADK (`streamQuery`) and A2A (`message:send`) surfaces, before and
   after it reaches the agent.
3. [ADK deployment findings](03-adk-deployment-findings.md) — what we found
   testing `financial-advisor-adk`: Gateway Model Armor does sanitize
   `streamQuery` ingress, and why the Security tab still lagged.
4. [A2A deployment findings](04-a2a-deployment-findings.md) — what we found
   testing `financial-advisor-a2a`: Gateway Model Armor does **not** run on
   `message:send` ingress (a documented product limitation), what still
   protects it, and the executor-side mitigation.
5. [Red-team test results](05-red-team-results.md) — the five adversarial
   prompts used to unit-test both agents, with the actual Model Armor log
   evidence (filters matched, verdicts, timestamps) pulled live from Cloud
   Logging for each one.
6. [Comparison & the real gaps](06-comparison-and-gaps.md) — ADK vs. A2A,
   what's possible vs. not, and the specific list of items that need a
   Google Cloud support ticket rather than a config change on our side.
7. [Support tickets to file](07-support-tickets.md) — ready-to-file drafts
   for all six gaps: title, product area, repro steps, evidence, and the
   exact questions to ask, plus a recommended filing order.

## Five-minute summary

- **Two independent Model Armor enforcement points exist**, and they behave
  differently:
  - **Gateway Model Armor** (`agentGatewayConfig` + template
    `financial-advisor-security`, region `us-central1`) sits in front of the
    agent and only inspects **ADK `streamQuery`** ingress. It does **not**
    run on A2A `message:send` — this is a documented Google product gap, not
    a misconfiguration ([details](04-a2a-deployment-findings.md)).
  - **Floor settings** (`AI_PLATFORM` integration, region `global`) inspect
    every **Gemini `generateContent`** call the agent makes internally —
    this runs for *both* deployments, since both eventually call Gemini, and
    it's the one control that gives A2A any Model Armor coverage today.
- **Both controls are logging real matches.** Live Cloud Logging queries
  confirm `MATCH_FOUND` sanitize events for all five red-team prompts
  ([evidence](05-red-team-results.md)) — Model Armor is working.
- **The agent-details console Security tab is still the weak link.** It
  aggregates from Cloud Trace spans (and likely SCC), not straight from
  these sanitize logs, so it can read "0" even while Logging shows real
  detections — see the [gap list](06-comparison-and-gaps.md#gaps-to-raise-with-google-cloud-support)
  for exactly what to ask Google.

## Related documents

- [`../agent-registry.md`](../agent-registry.md) — when Agent Registry
  registration is/isn't needed for these agents.

> This directory supersedes and replaces the earlier
> `docs/adk-model-armor-playground-flow.md` and
> `docs/a2a-model-armor-playground-flow.md` notes — their content has been
> folded into pages 3–5 above, with the raw notes removed to avoid two
> copies of the same findings drifting apart.
