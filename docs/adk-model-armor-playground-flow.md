# ADK Playground, Agent Gateway, and Model Armor — findings

This document records how prompts flow for **`financial-advisor-adk`** on Agent Engine, when Model Armor runs on **ingress**, and how that differs from the A2A twin.

**Companion (A2A gap):** [`a2a-model-armor-playground-flow.md`](./a2a-model-armor-playground-flow.md)

**Scope:** project `gemini-agent-101`, region `us-central1`, Reasoning Engine `4756172291677618176` (`financial-advisor-adk`), ingress gateway `financial-advisor-ingress-gw`, template `financial-advisor-security`.

---

## 1. Key findings (summary)

1. **Playground for ADK agents uses `streamQuery`** (typically `async_stream_query` / `stream_query` class methods), not A2A `message:send`.
2. **Agent Gateway Client-to-Agent Model Armor *does* sanitize ADK `streamQuery` ingress and responses** when the Reasoning Engine has `agent_gateway_config` pointing at a gateway with a Model Armor `CONTENT_AUTHZ` policy.
3. **Floor settings** on `AI_PLATFORM` can still apply later at Gemini `generateContent` if a prompt is allowed past the gateway.
4. **The agent Security tab** is more likely to show findings for this ADK path than for A2A Playground traffic, because Gateway Model Armor actually runs on `streamQuery`.
5. Display name was renamed from `financial_coordinator` → **`financial-advisor-adk`**, with the same ingress gateway + `AGENT_IDENTITY` pattern as `financial-advisor-a2a`.

---

## 2. End-to-end data flow (Playground / ADK client)

```text
Caller (Playground UI  OR  streamQuery REST client)
    │
    │  HTTPS + OAuth
    ▼
Agent Engine control plane
  POST …/reasoningEngines/{id}:streamQuery?alt=sse
  (class_method: async_stream_query | stream_query)
    │
    ▼
Client-to-Agent Gateway
  financial-advisor-ingress-gw
  (agent_gateway_config.client_to_agent_config)
    │
    ├─ Model Armor CONTENT_AUTHZ (template financial-advisor-security)
    │     ✓  Applied to ADK streamQuery request (+ response screening)
    │     ✕  Not applied to A2A message:send (see A2A doc)
    │
    ├─ If blocked → client gets error (MODEL_ARMOR / policy)
    │
    ▼
Reasoning Engine workers
  AdkApp → financial_coordinator + AgentTool sub-agents
    │
    ▼
Vertex Gemini generateContent
    │
    ├─ Model Armor floor settings (AI_PLATFORM)  ← may still apply
    ├─ Gemini built-in safety
    │
    ▼
SSE stream events → Playground / client
```

### Step table

| Step | Component | Runs for ADK? | Model Armor? |
|------|-----------|---------------|--------------|
| 1 | Playground / client sends prompt | Yes | — |
| 2 | Agent Engine `streamQuery` | Yes | — |
| 3 | Client-to-Agent Gateway | Yes | Configured |
| 4 | Gateway Model Armor (CONTENT_AUTHZ) | **Yes for `streamQuery`** | Ingress + response |
| 5 | ADK coordinator + tools | If allowed | — |
| 6 | Gemini `generateContent` | If allowed | Floor settings may apply |
| 7 | SSE events → Playground | Yes | Response may be screened |

---

## 3. ADK vs A2A (same gateway)

| Question | ADK (`financial-advisor-adk`) | A2A (`financial-advisor-a2a`) |
|---------|-------------------------------|--------------------------------|
| Playground API | `streamQuery` | `message:send` + `tasks.get` |
| Gateway attached? | Yes | Yes |
| Gateway Model Armor on ingress? | **Yes** | **No** (product coverage) |
| Security tab findings from jailbreak | More likely | Often empty |
| Resource ID | `4756172291677618176` | `6099511618029223936` |

---

## 4. Deploy / console checklist

| Piece | Value |
|-------|--------|
| Display name | `financial-advisor-adk` |
| Framework | `google-adk` |
| Gateway | `…/agentGateways/financial-advisor-ingress-gw` |
| Identity | `AGENT_IDENTITY` |
| Template | `financial-advisor-security` |
| Update | `uv run deployment/deploy.py --update --resource_id=…/4756172291677618176 …` |

Console: Agent Engine → **financial-advisor-adk** → Playground / Gateway / Security tabs.

---

## 5. Playground empty reply + Security tab = 0

### Empty Playground for the DAN / phishing prompt

**Update (2026-08-19):** Gateway template + floor settings were switched to **`INSPECT_ONLY`** so Playground gets a visible model reply (usually a refusal) instead of a blank 403. Violations are still logged. To hard-block again, set template `enforcementType` back to `INSPECT_AND_BLOCK` and floor `inspectAndBlock`.

Previously, with `INSPECT_AND_BLOCK`, the same prompt over REST returned HTTP 403 and Playground often showed **no chat text**.

Control check: `Hello — briefly introduce yourself as the financial advisor.` should return a normal reply.


### Where violations actually are (today)

Model Armor **is** recording matches. Example Logs Explorer filter:

```text
resource.type="modelarmor.googleapis.com/SanitizeOperation"
jsonPayload.sanitizationResult.filterMatchState="MATCH_FOUND"
jsonPayload.sanitizationResult.filterResults.pi_and_jailbreak.piAndJailbreakFilterResult.matchState="MATCH_FOUND"
```

[Open Logs Explorer (project gemini-agent-101)](https://console.cloud.google.com/logs/query;query=resource.type%3D%22modelarmor.googleapis.com%2FSanitizeOperation%22%0AjsonPayload.sanitizationResult.filterMatchState%3D%22MATCH_FOUND%22;project=gemini-agent-101)

Jailbreak hits show `pi_and_jailbreak` = `MATCH_FOUND` (often `HIGH`) plus RAI `dangerous`.

### Why the agent Security tab still shows 0

Google documents that the Security tab Model Armor widgets need:

1. Gateway + Model Armor (done)
2. **Tracing / telemetry spans** — widgets aggregate from Cloud Trace (`apply_guardrail "Google Cloud Model Armor"`), not from Logs Explorer alone
3. Prefer viewing via **Agent Registry → agent → Security**, and the **project-level** Agent Platform Security tab
4. Full “security findings” widgets also expect **Security Command Center** (Standard/Premium) + AI Protection

**Hard truth from this project’s testing:**

- With gateway **`INSPECT_AND_BLOCK`**, violating prompts get **403 before the agent runs**. You get Model Armor **logs**, but often **no agent session spans** for the Security tab to attribute → UI stays empty.
- With **`INSPECT_ONLY`**, requests reach the agent; Cloud Trace shows combined traces with both `apply_guardrail "Google Cloud Model Armor"` and `invoke_agent financial_coordinator` (verified). Even then, Agent Platform / agent-details **Security** widgets can lag or stay empty while Traces / Logs are populated.
- `AGENT_ENGINE_THREAT_DETECTION` may show `intended=ENABLED` but `effective=DISABLED` when org inheritance blocks it — that affects threat findings, not content logs.

**Where data actually is today (use these, not the empty Security counters):**

1. Agent **Traces** tab → look for `apply_guardrail "Google Cloud Model Armor"`
2. [Cloud Trace explorer](https://console.cloud.google.com/traces/explorer?project=gemini-agent-101) filter `span:apply_guardrail`
3. [Model Armor MATCH_FOUND logs](https://console.cloud.google.com/logs/query;query=resource.type%3D%22modelarmor.googleapis.com%2FSanitizeOperation%22%0AjsonPayload.sanitizationResult.filterMatchState%3D%22MATCH_FOUND%22;project=gemini-agent-101)
4. [SCC AI Security](https://console.cloud.google.com/security/risk/ai?project=gemini-agent-101) (Standard)

Also: a **gateway block happens before the agent runs**, so there is often **no agent span** to attribute the block to the agent-level widget. Logs / Model Armor sanitize ops are the reliable proof of violation.


### OTEL Cloud Logging 401 (fixed)

If Reasoning Engine stderr shows:

`opentelemetry.exporter.cloud_logging … Unauthenticated: 401`

with `AGENT_IDENTITY`, check deploy env for `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`. That flag makes AdkApp use Cloud Logging **gRPC** export, which does not support certificate-bound agent tokens ([adk-python#6328](https://github.com/google/adk-python/issues/6328)). Removing it forces the stdout structured-JSON path. Do **not** set `GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES=false` unless you accept weaker token binding.

---

## 6. Deploy note: ADK pickle / set_up rebuild



If `streamQuery` returns `TypeError: 'NoneType' object is not subscriptable` on `canonical_model`, the Agent Engine runtime ADK version disagreed with a cloudpickled `LlmAgent`. This deploy uses `FinancialAdvisorAdkApp` (`financial_advisor/adk_app.py`) to **re-import `root_agent` in `set_up`**, and pins `google-adk==2.6.0`.

---

## 7. Tests



| Suite | Purpose |
|-------|---------|
| `tests/test_adk_stream.py` | Unit: SSE parsing, Model Armor block detection, deploy wiring |
| `tests/test_adk_playground_live.py` (`pytest -m live`) | Live `create_session` + `streamQuery` (Playground-equivalent) |

```bash
.venv/bin/pytest tests/test_adk_stream.py -v
.venv/bin/pytest -m live tests/test_adk_playground_live.py -v
```

---

## 8. References

- [Integrate Model Armor with Agent Gateway](https://docs.cloud.google.com/model-armor/model-armor-agent-gateway-integration) — ingress: ADK `streamQuery` only
- [Use an ADK agent](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/use-an-adk-agent) — `streamQuery` REST shape
