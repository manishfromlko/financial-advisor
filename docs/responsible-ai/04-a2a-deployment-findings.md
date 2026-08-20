# 4. A2A deployment findings (`financial-advisor-a2a`)

**[← ADK findings](03-adk-deployment-findings.md)** | Next: [Red-team results](05-red-team-results.md)

## Contents

- [Summary](#summary)
- [What does protect A2A ingress today](#what-does-protect-a2a-ingress-today)
- [Why the Security tab looks empty](#why-the-security-tab-looks-empty)
- [Mitigation already in the executor](#mitigation-already-in-the-executor)
- [If you need A2A ingress actually guarded](#if-you-need-a2a-ingress-actually-guarded)
- [Tests](#tests)

## Summary

1. Playground and any external A2A client use the same protocol path — both
   call `message:send` / `tasks.get`. Who initiates the call does **not**
   change Model Armor behavior on ingress.
2. **Agent Gateway Client-to-Agent Model Armor does not sanitize A2A
   `message:send` ingress.** Google's docs describe ingress sanitization for
   **ADK `streamQuery`** only. This is a product coverage gap relative to
   the natural expectation that "gateway + Model Armor keeps every
   client→agent call safe" — see [gap #1](06-comparison-and-gaps.md#gaps-to-raise-with-google-cloud-support).
3. Model Armor can still apply later, when the agent calls Gemini via
   Vertex `generateContent`, through project **floor settings**
   (`AI_PLATFORM`) and Gemini's own safety filters.
4. The agent-details **Security tab** is marketed around Gateway + Model
   Armor findings. For A2A traffic that never hits Gateway Model Armor on
   ingress, that tab stays empty even when a jailbreak prompt clearly
   "fails" in the UI.
5. Empty Playground output for jailbreak prompts was usually **not** a
   hang: the A2A task completed with artifact text `"No response."`,
   because Gemini returned a final ADK event with no text parts. The
   executor now emits an explicit message instead (below).

## What does protect A2A ingress today

| Layer | Protects `message:send` ingress? | Notes |
|---|---|---|
| Gateway Model Armor (Client-to-Agent) | Effectively **no** | Docs: ADK `streamQuery` only |
| Floor settings on `generateContent` | **Partial** | Project-level; inspect + logging for `AI_PLATFORM`, confirmed live |
| Gemini built-in safety | Yes | Refusals / empty finals |
| Explicit `sanitizeUserPrompt` call in the executor | Not yet implemented | The reliable, owned fix — see below |
| Egress Gateway Model Armor | Different hop | Protects agent → tools/MCP/other-agent calls, not this ingress |

Verified directly against the Model Armor API: calling `generateContent`
with `modelArmorConfig` pointing at the floor template returns
`blockReason: MODEL_ARMOR` for a jailbreak-style prompt, and the template's
own `sanitizeUserPrompt` returns `MATCH_FOUND` on PI/jailbreak (and SDP for
test SSN/credit-card strings) — that part of the pipeline genuinely works,
it's just downstream of the agent already having started running.

## Why the Security tab looks empty

1. Gateway Model Armor **does not** sanitize `message:send`, so there is no
   ingress-level finding for the console to show at all for that hop.
2. Failures typically appear as **empty model text** or a Gemini refusal
   inside the agent — not as a Security-dashboard row.
3. The reliable evidence is elsewhere:
   - Model Armor console / findings
   - Cloud Logging (`SanitizeOperationLogEntry`, floor-setting entries —
     these do have full request text, see [page 5](05-red-team-results.md))
   - Security Command Center (tier/config permitting)

## Mitigation already in the executor

[`financial_advisor/a2a_executor.py`](../../financial_advisor/a2a_executor.py)
tracks the last non-empty model text across streamed ADK events and, if the
final event genuinely has no text parts (the common shape for a
blocked/refused jailbreak turn), returns an explicit message instead of a
silent `"No response."`:

```python
EMPTY_FINAL_RESPONSE_MESSAGE = (
    "The model returned no text for this turn. "
    "This often means Gemini safety filters or "
    "Model Armor blocked the prompt/response. "
    "Check Model Armor / Security findings, or "
    "retry with a normal request such as: Analyze AAPL"
)
```

This fixes the *user-visible confusion* (blank reply looked like a hang or
bug) but is not a security control by itself — it doesn't stop anything
from reaching the model, it just explains what happened after the fact.

## If you need A2A ingress actually guarded

Practical options until Gateway covers A2A `message:send` ingress:

1. **Call Model Armor directly in `FinancialAdvisorAgentExecutor`** before
   `runner.run_async` (template `financial-advisor-security`) — reject or
   rewrite on `MATCH_FOUND`. This is the recommended next step; it's the
   only option in this list that's fully in our control.
2. Keep floor settings for Gemini calls (already on).
3. Use **egress** gateway protection when this agent calls other A2A/MCP
   endpoints.
4. For a Security-tab / documented Gateway Model Armor ingress demo, use
   **`financial-advisor-adk`** with **`streamQuery`** through the same
   ingress gateway instead — see [page 3](03-adk-deployment-findings.md).
5. Treat Security-tab emptiness on A2A Playground as **expected** given
   current product coverage, not a bug to keep chasing on our side.

## Tests

| Suite | Purpose |
|---|---|
| `tests/unit/test_a2a_executor.py` | Final text, fallback text, empty-final → guidance message, jailbreak empty-parts handling |
| `tests/live/test_a2a_playground_live.py` (`pytest -m live`) | Live A2A `message:send` + `tasks.get` (Playground-equivalent) against the deployed engine |

```bash
uv run pytest tests/unit/test_a2a_executor.py -v
uv run pytest -m live tests/live/test_a2a_playground_live.py -v
```

## Naming note (Agent Engine console)

The console page opened by clicking a deployment (tabs such as Playground,
Security, Traces, Sessions, …) is the **agent-details** / **deployment
details** view for that Agent Engine / Agent Runtime instance (sometimes
described as the Agent Platform instance page). The chat surface on it is
the **Playground** tab.
