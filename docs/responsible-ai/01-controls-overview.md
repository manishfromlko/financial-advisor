# 1. Controls overview

**[← Back to index](README.md)** | Next: [Request → response flow](02-request-response-flow.md)

## Contents

- [What each control actually is](#what-each-control-actually-is)
- [How they're wired in this project](#how-theyre-wired-in-this-project)
- [Live-verified configuration (2026-08-20)](#live-verified-configuration-2026-08-20)

## What each control actually is

It's easy to conflate these four names — they are four different products,
enforced at four different points in the request path.

| Control | What it is | Enforcement point |
|---|---|---|
| **Agent Gateway** | A client-to-agent ingress proxy that sits in front of an Agent Engine (Reasoning Engine) deployment. Routes/authenticates traffic and can attach extensions (like Model Armor) before the request reaches the agent. | Network edge, in front of the Reasoning Engine |
| **Model Armor — Gateway template** (`CONTENT_AUTHZ` policy) | A named Model Armor template (here: `financial-advisor-security`) attached to the Agent Gateway. Inspects prompts/responses for prompt injection & jailbreak, sensitive-data (SDP/PII), responsible-AI categories (hate, harassment, dangerous, sexual), and malicious URIs. | **Only on the ingress protocol Google has wired it for today: ADK `streamQuery`.** Does not run on A2A `message:send` (see [page 4](04-a2a-deployment-findings.md)). |
| **Model Armor — Floor settings** (`AI_PLATFORM` integration) | A project-level Model Armor configuration that screens every Vertex **`generateContent`** call, independent of how the request arrived. | Inside the agent's own calls to Gemini — runs for **both** ADK and A2A, because both eventually call `generateContent`. |
| **Security Command Center (SCC) / AI Protection** | Google Cloud's organization-level security findings platform. Model Armor and Agent Engine threat detection can feed findings into it. Full "security findings" widgets on the agent-details page are documented as depending on this. | Organization-scoped; separate IAM surface from project-level roles (see [gap #3](06-comparison-and-gaps.md#gaps-to-raise-with-google-cloud-support)). |
| **Agent Engine Threat Detection** (`AGENT_ENGINE_THREAT_DETECTION`) | A per-project toggle for agent-specific threat findings (e.g. anomalous tool use). Can show `intended=ENABLED` but `effective=DISABLED` when org policy inheritance blocks it. | Console/API setting; effective status was not directly queryable via the APIs available to us this session. |

## How they're wired in this project

Both Reasoning Engines are created/updated by
[`deployment/deploy.py`](../../deployment/deploy.py) with the same ingress
gateway:

```python
INGRESS_AGENT_GATEWAY = (
    "projects/gemini-agent-101/locations/us-central1/"
    "agentGateways/financial-advisor-ingress-gw"
)

def _ingress_gateway_config() -> dict[str, Any]:
    return {"client_to_agent_config": {"agent_gateway": INGRESS_AGENT_GATEWAY}}
```

...applied to both `create`/`update` (ADK) and `create_a2a`/`update_a2a`
(A2A), alongside `identity_type: "AGENT_IDENTITY"` so the deployment gets a
Workload Identity Federation-style agent identity rather than a shared
service account.

The Model Armor **template** and **floor settings** themselves are not
managed as code in this repo — they're configured directly against the
Model Armor API/console (there is no Terraform/YAML for them here). This
doc records their state as observed live, since that's the part that drifts.

## Live-verified configuration (2026-08-20)

Pulled directly from the Model Armor API and the Reasoning Engine API
(commands and full output are in this investigation's session notes; only
the results are reproduced here so this page doesn't rot into a shell
transcript):

**Gateway template `financial-advisor-security`** (`us-central1`):

| Setting | Value |
|---|---|
| `enforcementType` | `INSPECT_ONLY` (switched from `INSPECT_AND_BLOCK` on 2026-08-19 — see [page 3](03-adk-deployment-findings.md)) |
| `logSanitizeOperations` / `logTemplateOperations` | `true` / `true` |
| RAI filters | Hate speech, harassment, dangerous, sexually explicit — all `MEDIUM_AND_ABOVE` |
| SDP (PII) filter | `ENABLED` (basic config) |
| PI & jailbreak filter | `ENABLED`, `LOW_AND_ABOVE` |
| Malicious URI filter | `ENABLED` |
| `dataResidencyCompliant` | `true` — **this matters**, see [gap #6](06-comparison-and-gaps.md#gaps-to-raise-with-google-cloud-support) |

**Project floor settings** (`global`, `AI_PLATFORM` + `GOOGLE_MCP_SERVER`):

| Setting | Value |
|---|---|
| `enableFloorSettingEnforcement` | `true` |
| `aiPlatformFloorSetting.inspectOnly` | `true` |
| `aiPlatformFloorSetting.enableCloudLogging` | `true` |
| Filter config | Same categories/thresholds as the gateway template (RAI `MEDIUM_AND_ABOVE`, PI/jailbreak `LOW_AND_ABOVE`, SDP + malicious URI enabled) |

**Both Reasoning Engines** (`describe` against the Agent Engine API):

| Field | `financial-advisor-adk` | `financial-advisor-a2a` |
|---|---|---|
| `agentGatewayConfig.clientToAgentConfig.agentGateway` | `financial-advisor-ingress-gw` | `financial-advisor-ingress-gw` |
| `identityType` | `AGENT_IDENTITY` | `AGENT_IDENTITY` |
| `effectiveIdentity` | present, resolved | present, resolved |
| Last updated | `2026-08-19T19:14:24Z` | `2026-08-19T17:54:59Z` |

Both engines are correctly wired to the gateway with a resolved agent
identity — the wiring is not the problem. What differs is which *protocol*
each one speaks, and that's what determines whether Gateway Model Armor
actually runs (next page).
