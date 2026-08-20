# 3. ADK deployment findings (`financial-advisor-adk`)

**[← Request/response flow](02-request-response-flow.md)** | Next: [A2A findings](04-a2a-deployment-findings.md)

## Contents

- [Summary](#summary)
- [Timeline: block → inspect-only](#timeline-block--inspect-only)
- [Why the Security tab still showed 0](#why-the-security-tab-still-showed-0)
- [Where the evidence actually lives](#where-the-evidence-actually-lives)
- [Deploy checklist](#deploy-checklist)
- [Tests](#tests)

## Summary

1. Playground for the ADK agent (and any direct client) uses `streamQuery`
   (`async_stream_query` / `stream_query`), not A2A `message:send`.
2. **Gateway Model Armor *does* sanitize `streamQuery` ingress and
   responses**, because the Reasoning Engine's `agent_gateway_config`
   points at a gateway with a Model Armor `CONTENT_AUTHZ` policy attached,
   and Google documents ingress coverage for ADK `streamQuery`
   specifically.
3. Floor settings on `AI_PLATFORM` still apply later, at Gemini
   `generateContent`, if a prompt gets past the gateway.
4. The agent-details **Security tab** is more likely to show findings for
   this ADK path than for A2A traffic, because Gateway Model Armor actually
   runs here — but "more likely" isn't "reliably," see below.

## Timeline: block → inspect-only

The gateway template `financial-advisor-security` was switched from
`INSPECT_AND_BLOCK` to `INSPECT_ONLY` on **2026-08-19 at 19:20:52 UTC**,
mid-investigation. Live log evidence brackets this cleanly:

- **Before the switch** (17:42–19:14 UTC): gateway-attributed sanitize log
  entries for jailbreak/dangerous-content prompts show
  `sanitizationVerdict: MODEL_ARMOR_SANITIZATION_VERDICT_BLOCK`.
- **After the switch** (19:21+ UTC): the same class of prompts produce
  `sanitizationVerdict: MODEL_ARMOR_SANITIZATION_VERDICT_ALLOW`, with a
  `sanitizationVerdictReason` explicitly stating *"input was not blocked as
  the enforcement type is inspect only."*

Under `INSPECT_AND_BLOCK`, a violating prompt gets HTTP 403 **before the
agent runs at all** — Playground often showed no chat text for a blocked
turn. Under `INSPECT_ONLY`, the request reaches the agent and Playground
gets a visible model reply (usually a refusal), while the violation is
still logged. Control check used throughout: `Hello — briefly introduce
yourself as the financial advisor.` should always return a normal reply
regardless of enforcement mode.

To go back to hard-blocking, set the template's `enforcementType` back to
`INSPECT_AND_BLOCK` (and the floor setting's `inspectAndBlock` if you want
that layer to hard-block too — it does not today, see
[page 1](01-controls-overview.md)).

## Why the Security tab still showed 0

Even with real `MATCH_FOUND` sanitize log entries for this exact deployment
(see [page 5](05-red-team-results.md) for the specific prompts and
timestamps), the agent-details **Security** tab widgets stayed at 0. Based
on what we could observe and what Google's docs say the widgets aggregate
from:

1. **The tab aggregates from Cloud Trace spans** (`apply_guardrail "Google
   Cloud Model Armor"`), not from these raw sanitize logs directly.
2. With `INSPECT_AND_BLOCK`, a violating prompt is rejected **before an
   agent session span exists** — there is nothing for the console to
   attribute a finding to, even though Model Armor logged the match.
3. With `INSPECT_ONLY`, requests reach the agent and Cloud Trace does show
   combined traces with both `apply_guardrail "Google Cloud Model Armor"`
   and `invoke_agent financial_coordinator` spans (verified) — but the
   agent-details Security widgets can still lag or stay empty while
   Traces/Logs are already populated.
4. Full "security findings" widgets are additionally documented as
   expecting **Security Command Center (Standard/Premium) + AI Protection**
   — see [gap #3](06-comparison-and-gaps.md#gaps-to-raise-with-google-cloud-support)
   for why we couldn't confirm this project's tier from the API.
5. `AGENT_ENGINE_THREAT_DETECTION` can show `intended=ENABLED` but
   `effective=DISABLED` when org-policy inheritance blocks it — that
   affects threat findings specifically, not content/sanitize logs.

## Where the evidence actually lives

Don't rely on the Security tab counters. These reliably show the same
violations:

1. **Traces** tab on the agent → look for `apply_guardrail "Google Cloud
   Model Armor"` spans.
2. [Cloud Trace explorer](https://console.cloud.google.com/traces/explorer?project=gemini-agent-101),
   filter `span:apply_guardrail`.
3. [Model Armor `MATCH_FOUND` logs](https://console.cloud.google.com/logs/query;query=resource.type%3D%22modelarmor.googleapis.com%2FSanitizeOperation%22%0AjsonPayload.sanitizationResult.filterMatchState%3D%22MATCH_FOUND%22;project=gemini-agent-101).
4. [SCC AI Security](https://console.cloud.google.com/security/risk/ai?project=gemini-agent-101) (tier permitting).

## Deploy checklist

| Piece | Value |
|---|---|
| Display name | `financial-advisor-adk` |
| Framework | `google-adk` |
| Gateway | `projects/gemini-agent-101/locations/us-central1/agentGateways/financial-advisor-ingress-gw` |
| Identity | `AGENT_IDENTITY` |
| Model Armor template | `financial-advisor-security` |
| Update | `uv run deployment/deploy.py --update --resource_id=.../4756172291677618176 ...` |

Console: Agent Engine → **financial-advisor-adk** → Playground / Gateway /
Security / Traces tabs.

A separate, unrelated deploy gotcha worth keeping here: if `streamQuery`
returns `TypeError: 'NoneType' object is not subscriptable` on
`canonical_model`, the Agent Engine runtime's ADK version disagreed with a
cloudpickled `LlmAgent`. This deploy uses `FinancialAdvisorAdkApp`
([`financial_advisor/adk_app.py`](../../financial_advisor/adk_app.py)) to
re-import `root_agent` in `set_up`, and pins `google-adk==2.6.0` in
[`deployment/deploy.py`](../../deployment/deploy.py).

## Tests

| Suite | Purpose |
|---|---|
| `tests/unit/test_adk_stream.py` | SSE parsing, Model Armor block-detection heuristics, deploy wiring |
| `tests/live/test_adk_playground_live.py` (`pytest -m live`) | Live `create_session` + `streamQuery` (Playground-equivalent) against the deployed engine |

```bash
uv run pytest tests/unit/test_adk_stream.py -v
uv run pytest -m live tests/live/test_adk_playground_live.py -v
```
