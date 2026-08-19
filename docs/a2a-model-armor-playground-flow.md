# A2A Playground, Agent Gateway, and Model Armor — findings

This document records how prompts flow for **`financial-advisor-a2a`** on Agent Engine, when Model Armor actually runs, and why the Security tab often stays empty. It matches the interactive map in Cursor:

- Canvas: `.cursor/projects/.../canvases/playground-model-armor-flow.canvas.tsx` (open beside chat in Cursor)

**Scope:** project `gemini-agent-101`, region `us-central1`, Reasoning Engine `6099511618029223936` (`financial-advisor-a2a`), ingress gateway `financial-advisor-ingress-gw`, template `financial-advisor-security`.

---

## 1. Key findings (summary)

1. **Playground and external A2A clients use the same protocol path** — both call A2A APIs such as `message:send` / `tasks.get`. Who initiates the call does **not** change Model Armor behavior on ingress.
2. **Agent Gateway Client-to-Agent Model Armor does not sanitize A2A `message:send` ingress.** Google documents ingress sanitization for **ADK `streamQuery`** only. That is a product coverage gap relative to the expectation that “gateway + Model Armor keeps every client→agent call safe.”
3. **Model Armor can still apply later** when the agent calls Gemini via Vertex **`generateContent`**, via project **floor settings** (`AI_PLATFORM` / Vertex AI integration) and Gemini’s own safety filters.
4. **The agent Security tab** is marketed around Gateway + Model Armor (+ often Google MCP) findings. For A2A Playground traffic that never hits Gateway Model Armor on ingress, that tab often stays empty even when jailbreak prompts “fail” in the UI.
5. **Empty Playground output** for jailbreak prompts was usually **not** a hang: the A2A task completed with artifact text `"No response."` because Gemini returned a final ADK event with no text parts. The executor now emits an explicit empty-final / possible-block message instead.

---

## 2. End-to-end data flow (Playground / A2A client)

```text
Caller (Playground UI  OR  external A2A client)
    │
    │  HTTPS + OAuth
    ▼
Agent Engine control plane
  POST …/reasoningEngines/{id}/a2a/v1/message:send
  GET  …/a2a/v1/tasks/{taskId}
    │
    ▼
Client-to-Agent Gateway
  financial-advisor-ingress-gw
  (agent_gateway_config.client_to_agent_config on the ReasoningEngine)
    │
    ├─ Model Armor CONTENT_AUTHZ (template financial-advisor-security)
    │     ✕  NOT applied to A2A SendMessage / message:send
    │     ✓  Documented for ADK streamQuery ingress only
    │
    ▼
Reasoning Engine workers
  A2A HTTP server
    → FinancialAdvisorAgentExecutor
    → ADK Runner (financial_coordinator + AgentTool sub-agents)
    → GCS task store gs://…/a2a_tasks/
    │
    ▼
Vertex Gemini generateContent (gemini-2.5-pro)
    │
    ├─ Model Armor floor settings (AI_PLATFORM)  ← can inspect/block HERE
    ├─ Gemini built-in safety
    │
    ▼
A2A task artifact ("answer")
    │
    ▼
Caller renders response (Playground polls tasks.get)
```

### Step table

| Step | Component | Runs for A2A? | Model Armor? |
|------|-----------|---------------|--------------|
| 1 | Playground / A2A client sends prompt | Yes | — |
| 2 | Agent Engine A2A API | Yes | — |
| 3 | Client-to-Agent Gateway (attached) | Associated / on path | Configured |
| 4 | Gateway Model Armor (CONTENT_AUTHZ) | **Skipped for A2A `message:send`** | No |
| 5 | A2A executor → ADK coordinator | Yes | Optional if you call sanitize APIs in code |
| 6 | Gemini `generateContent` | Yes | Floor settings **may** apply |
| 7 | Task artifact → Playground / client | Yes | — |

---

## 3. Playground vs external A2A client

| Question | Answer |
|---------|--------|
| Does an external A2A client change Gateway Model Armor behavior? | **No.** Same A2A ingress payload class. |
| Will Gateway Model Armor sanitize `message:send` if not from Playground? | **No** (per current Agent Gateway + Model Armor docs). |
| Is A2A “meant” for client↔agent / agent↔agent? | Yes — that expectation is correct; **ingress Gateway Model Armor coverage for A2A is incomplete today.** |

This is a **product limitation**, not an argument that A2A needs no protection.

---

## 4. What *does* protect the agent today

| Layer | Protects A2A `message:send` ingress? | Notes |
|-------|--------------------------------------|-------|
| Gateway Model Armor (Client-to-Agent) | Effectively **no** for A2A | Docs: ADK `streamQuery` only |
| Floor settings on Vertex `generateContent` | **Partial** | Project-level; inspect/block + logging for AI_PLATFORM |
| Gemini built-in safety | **Yes** | Refusals / empty finals |
| Explicit `sanitizeUserPrompt` / template in executor | **Yes, if implemented** | Reliable control you own |
| Egress Gateway Model Armor | Different hop | Agent → tools / MCP / other agents; some A2A egress payloads can be sanitized |

### Configured in this project (as of Aug 2026)

- Floor settings: RAI, PI/jailbreak (`LOW_AND_ABOVE`), SDP basic, malicious URI; `INSPECT_AND_BLOCK` + logging for `AI_PLATFORM` and `GOOGLE_MCP_SERVER`.
- Template: `projects/gemini-agent-101/locations/us-central1/templates/financial-advisor-security`.
- Gateway: `projects/gemini-agent-101/locations/us-central1/agentGateways/financial-advisor-ingress-gw` with Model Armor authz extension + `CONTENT_AUTHZ` policy.
- Agent: `agent_gateway_config` + `AGENT_IDENTITY` on `financial-advisor-a2a`.

Verified: `generateContent` with `modelArmorConfig` pointing at the template returns `blockReason: MODEL_ARMOR` for a jailbreak-style prompt. Direct template `sanitizeUserPrompt` returns `MATCH_FOUND` on PI/jailbreak (and SDP for test CC/SSN strings).

---

## 5. Why the Security tab looks empty

The agent details **Security** UI is aimed at Model Armor findings tied to **Agent Gateway** (and related) enforcement. For A2A Playground / A2A client traffic:

1. Gateway Model Armor **does not** sanitize `message:send`.
2. Failures often appear as **empty model text** or Gemini refusals inside the agent, not as Security-dashboard rows.
3. Floor-setting / sanitize evidence is more reliably found in:
   - Model Armor console / findings  
   - Cloud Logging (`SanitizeOperationLogEntry`)  
   - Security Command Center (depending on tier/config)

**Jailbreak “blank” Playground output:** task completed with artifact `"No response."` (empty final ADK parts). Executor now surfaces `EMPTY_FINAL_RESPONSE_MESSAGE` instead. That is **not** the same as a Security-tab Model Armor violation.

---

## 6. If you need A2A ingress actually guarded

Practical options until Gateway covers A2A `message:send` ingress:

1. **Call Model Armor in `FinancialAdvisorAgentExecutor`** before `runner.run_async` (template `financial-advisor-security`) — reject or rewrite on `MATCH_FOUND`.
2. Keep **floor settings** for Gemini calls.
3. Use **egress** gateway protection when this agent calls other A2A/MCP endpoints.
4. For Security-tab / documented Gateway Model Armor ingress demos, use **`financial-advisor-adk`** with **`streamQuery`** through the same ingress gateway — see [`adk-model-armor-playground-flow.md`](./adk-model-armor-playground-flow.md).
5. Treat Security-tab emptiness on A2A Playground as **expected** with current product coverage.

---

## 7. Related tests

| Suite | Purpose |
|-------|---------|
| `tests/test_a2a_executor.py` | Unit: final text, fallback text, empty final → guidance, jailbreak empty parts |
| `tests/test_a2a_playground_live.py` (`pytest -m live`) | Live A2A `message:send` + `tasks.get` (Playground-equivalent) |

```bash
.venv/bin/pytest tests/test_a2a_executor.py -v
.venv/bin/pytest -m live tests/test_a2a_playground_live.py -v
```

---

## 8. Naming note (Agent Engine UI)

The console page opened by clicking a deployment (tabs such as Playground, Security, Traces, Sessions, …) is the **agent details** / **deployment details** view for that Agent Engine / Agent Runtime instance (sometimes described as the Agent Platform instance page). The chat surface on it is the **Playground** tab.

---

## 9. References

- [Integrate Model Armor with Agent Gateway](https://docs.cloud.google.com/model-armor/model-armor-agent-gateway-integration) — ingress: ADK `streamQuery` only; A2A notes under egress.
- [Configure Model Armor on a gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/configure-model-armor)
- [Integrate Model Armor with Gemini Enterprise Agent Platform (floor settings)](https://docs.cloud.google.com/model-armor/model-armor-vertex-integration)
- [Route Agent Runtime traffic through Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-gateway-runtime-deploy)
