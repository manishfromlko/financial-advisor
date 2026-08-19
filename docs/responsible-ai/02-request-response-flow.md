# 2. Request → response flow

**[← Controls overview](01-controls-overview.md)** | Next: [ADK findings](03-adk-deployment-findings.md)

## Contents

- [ADK flow: `streamQuery`](#adk-flow-streamquery)
- [A2A flow: `message:send`](#a2a-flow-messagesend)
- [Side-by-side step table](#side-by-side-step-table)

Both diagrams show the **full round trip** — caller in, GCP components in
the middle, agent response out — for one user turn. The only structural
difference between them is whether **Gateway Model Armor** sits in the path
at all; everything after "Reasoning Engine worker" is otherwise the same
ADK agent underneath.

## ADK flow: `streamQuery`

Used by the Agent Engine **Playground** (for the ADK agent) and any direct
`streamQuery` REST/SDK client.

```mermaid
sequenceDiagram
    autonumber
    participant C as Caller<br/>(Playground / streamQuery client)
    participant AE as Agent Engine<br/>control plane
    participant GW as Agent Gateway<br/>financial-advisor-ingress-gw
    participant MA1 as Model Armor<br/>Gateway template<br/>(financial-advisor-security)
    participant RE as Reasoning Engine worker<br/>(FinancialAdvisorAdkApp)
    participant AGT as financial_coordinator<br/>+ sub-agents (AgentTool)
    participant GEM as Vertex Gemini<br/>generateContent
    participant MA2 as Model Armor<br/>Floor setting (AI_PLATFORM)

    C->>AE: HTTPS + OAuth<br/>POST reasoningEngines/{id}:streamQuery
    AE->>GW: forward (agent_gateway_config.client_to_agent_config)
    GW->>MA1: sanitizeUserPrompt (CONTENT_AUTHZ)
    alt MATCH_FOUND and enforcementType=INSPECT_AND_BLOCK
        MA1-->>C: HTTP 403 (blocked before agent runs — no agent span)
    else ALLOW (INSPECT_ONLY, or no match)
        MA1-->>GW: allow (+ Cloud Logging entry)
        GW->>RE: forward request
        RE->>AGT: runner.run_async(query)
        AGT->>GEM: generateContent (coordinator and/or sub-agent calls)
        GEM->>MA2: floor-setting inspect (AI_PLATFORM)
        MA2-->>GEM: allow/log (inspect only, + Cloud Logging entry)
        GEM-->>AGT: model response
        AGT-->>RE: final ADK event
        RE-->>GW: SSE stream
        GW-->>AE: SSE stream
        AE-->>C: SSE events (alt=sse)
    end
```

**Key point:** Gateway Model Armor (`MA1`) is a real pre-agent checkpoint
here — a blocked prompt never reaches `financial_coordinator` at all, which
is exactly why a blocking verdict leaves no agent trace/span for the
console Security tab to attribute a finding to (see [page 3](03-adk-deployment-findings.md)).

## A2A flow: `message:send`

Used by the Agent Engine Playground (for the A2A agent) and any external
A2A client. Playground and external clients are indistinguishable to the
gateway — both use the same `message:send` / `tasks.get` shape.

```mermaid
sequenceDiagram
    autonumber
    participant C as Caller<br/>(Playground / external A2A client)
    participant AE as Agent Engine<br/>control plane
    participant GW as Agent Gateway<br/>financial-advisor-ingress-gw<br/>(attached, on path)
    participant RE as Reasoning Engine worker<br/>(A2A HTTP server)
    participant EX as FinancialAdvisorAgentExecutor
    participant TS as GCS task store<br/>gs://.../a2a_tasks/
    participant AGT as financial_coordinator<br/>+ sub-agents (AgentTool)
    participant GEM as Vertex Gemini<br/>generateContent
    participant MA2 as Model Armor<br/>Floor setting (AI_PLATFORM)

    C->>AE: HTTPS + OAuth<br/>POST reasoningEngines/{id}/a2a/v1/message:send
    AE->>GW: forward (gateway attached, associated with the call)
    Note over GW: Gateway Model Armor CONTENT_AUTHZ is<br/>documented for ADK streamQuery ingress only —<br/>NOT applied to A2A message:send. Request passes through unscreened.
    GW->>RE: forward request (no Model Armor ingress check)
    RE->>EX: execute(context, event_queue)
    EX->>TS: get_or_create_session / save task
    EX->>AGT: runner.run_async(query)
    AGT->>GEM: generateContent (coordinator and/or sub-agent calls)
    GEM->>MA2: floor-setting inspect (AI_PLATFORM)
    MA2-->>GEM: allow/log (inspect only, + Cloud Logging entry)
    GEM-->>AGT: model response
    AGT-->>EX: final ADK event (may have empty text parts if blocked/refused)
    EX->>TS: save task artifact ("answer")
    C->>AE: GET reasoningEngines/{id}/a2a/v1/tasks/{taskId}
    AE->>GW: forward (poll)
    GW->>RE: forward (poll)
    RE-->>GW: task status + artifact
    GW-->>AE: task status + artifact
    AE-->>C: task status + artifact
```

**Key point:** there is no `MA1`-equivalent checkpoint in this diagram —
that's the actual gap, not a rendering omission. The only Model Armor
coverage A2A gets today is `MA2` (floor settings on the agent's own
`generateContent` calls), which is why [`a2a_executor.py`](../../financial_advisor/a2a_executor.py)
also does its own empty-final-response handling as a mitigation (see
[page 4](04-a2a-deployment-findings.md)).

## Side-by-side step table

| Step | ADK (`streamQuery`) | A2A (`message:send`) |
|---|---|---|
| 1. Caller → Agent Engine control plane | Yes | Yes |
| 2. Agent Gateway on path | Yes | Yes |
| 3. Gateway Model Armor screens ingress | **Yes** | **No** (product coverage gap) |
| 4. Reaches Reasoning Engine worker | If allowed by step 3 | Always (step 3 doesn't gate it) |
| 5. ADK coordinator + `AgentTool` sub-agents run | If allowed | Yes |
| 6. Floor-setting Model Armor screens `generateContent` | Yes | Yes |
| 7. Response returned to caller | SSE stream | Task artifact via poll |
