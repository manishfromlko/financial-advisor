# 6. Comparison & the real gaps

**[← Red-team results](05-red-team-results.md)** | [Back to index](README.md)

## Contents

- [ADK vs. A2A: what's possible and what's not](#adk-vs-a2a-whats-possible-and-whats-not)
- [Gaps to raise with Google Cloud support](#gaps-to-raise-with-google-cloud-support)
- [What to do on our side regardless](#what-to-do-on-our-side-regardless)

## ADK vs. A2A: what's possible and what's not

| Capability | ADK (`streamQuery`) | A2A (`message:send`) | Notes |
|---|---|---|---|
| Agent Gateway attached | ✅ Yes | ✅ Yes | Both point at `financial-advisor-ingress-gw`; wiring is identical |
| **Gateway Model Armor screens ingress** | ✅ Yes | ❌ **No** | Documented product limitation — gateway `CONTENT_AUTHZ` only covers ADK `streamQuery` today |
| Floor-setting Model Armor screens `generateContent` | ✅ Yes | ✅ Yes | Runs regardless of ingress protocol — both surfaces get this baseline |
| Prompt-injection / jailbreak detection (some layer) | ✅ Yes (2 layers) | ✅ Yes (1 layer — floor only) | ADK has defense in depth here; A2A has one layer |
| SDP/PII detection (some layer) | ✅ Yes (2 layers) | ✅ Yes (1 layer — floor only) | Same asymmetry |
| Malicious-URI detection (some layer) | ✅ Yes (2 layers) | ⚠️ Floor only, unverified whether it fires reliably outside gateway | Only gateway-surface hit was observed for this filter in testing |
| RAI dangerous/harassment detection | ⚠️ Inconsistent even within ADK (see [prompt 1](05-red-team-results.md#prompt-1--dan-jailbreak--phishing-content)) | ⚠️ Same inconsistency, floor-only | Not an ADK/A2A difference — a Model Armor classifier-consistency issue, see gap #4 |
| Explicit in-code Model Armor call before the agent runs | Not needed (gateway covers it) | ❌ Not implemented (`a2a_executor.py` only has the empty-response fallback) | Recommended fix on our side — see below |
| Agent-details console **Security tab** populated | ⚠️ Partial, lags/empties even when Traces/Logs show real matches | ❌ Effectively never for gateway-attributable findings, since gateway never runs; floor-only findings' attribution to this tab is unconfirmed | Neither is "solved"; ADK is closer |
| Reliable evidence of a violation | ✅ Traces (`apply_guardrail`) + Logs | ✅ Logs only (floor surface) | Both work if you stop looking at the Security tab |
| Empty/blocked-turn UX in Playground | Raw blank on hard-block; refusal text on inspect-only | Explicit `EMPTY_FINAL_RESPONSE_MESSAGE` guidance (executor-side fix already shipped) | A2A actually has the better UX here, ironically because we had to build it ourselves |

## Gaps to raise with Google Cloud support

These are the items where we've confirmed the behavior live but can't fix
it from our side — they need a support ticket / product feedback, not a
config change.

1. **Product gap — no Gateway Model Armor coverage for A2A ingress.**
   `financial-advisor-a2a`'s `message:send` traffic never reaches the
   `CONTENT_AUTHZ` policy attached to the same gateway that protects the
   ADK sibling. Ask: is A2A ingress coverage on the roadmap, and what's the
   ETA? Until then, is explicit in-executor `sanitizeUserPrompt` the
   *recommended* mitigation, or is there a supported gateway-level option
   we're missing?

2. **Console gap — Security tab reads 0 despite confirmed `MATCH_FOUND`
   logs.** Reproducible on `financial-advisor-adk` even under
   `INSPECT_ONLY` with Cloud Trace showing combined `apply_guardrail` +
   `invoke_agent` spans. Ask: what does the tab actually aggregate from
   (Trace only? SCC? both?), what's the expected latency, and will it ever
   reflect floor-setting-only findings for a surface (A2A) where the
   gateway itself never fires?

3. **IAM gap — SCC/AI Protection reads denied even for a project Owner.**
   `securitycenter.findings.list` returned `PERMISSION_DENIED` at the
   organization scope for our test account, despite `roles/owner` on the
   project — SCC permissions are organization-scoped and don't inherit from
   project `Owner`. Ask: what's the minimum org-level role needed to view
   AI Protection/SCC findings for an Agent Engine deployment, and is that
   the same role a console user needs to see the agent-details Security
   tab populate (if it depends on SCC)?

4. **Classifier-consistency gap — Gateway vs. Floor disagree on identical
   text.** The same DAN/phishing prompt ([prompt 1](05-red-team-results.md#prompt-1--dan-jailbreak--phishing-content))
   tripped `rai:dangerous` on the Gateway template but not on the Floor
   setting, one second apart, with what should be the same configured
   category/threshold. Ask: do the gateway `CONTENT_AUTHZ` template and
   `AI_PLATFORM` floor setting run the same model version and confidence
   calibration for RAI categories? If not, which one should we treat as
   authoritative for detection coverage claims?

5. **Confidence-tuning gap — RAI dangerous/harassment under-fired on an
   explicit weapons+threats prompt.** [Prompt 5](05-red-team-results.md#prompt-5--dangerous-content--threats)
   was caught only via `pi_and_jailbreak` riding on incidental jailbreak
   framing — `rai:dangerous`/`rai:harassment` at `MEDIUM_AND_ABOVE` never
   matched in any sampled hit. Ask: for a consumer-facing financial agent,
   is `LOW_AND_ABOVE` the recommended threshold for `dangerous`/
   `harassment`, and would a dangerous-content request phrased *without*
   jailbreak language be missed entirely at our current settings?

6. **Endpoint gap — `dataResidencyCompliant` templates return a misleading
   403 on the wrong hostname.** Reading the `financial-advisor-security`
   template via the default/global Model Armor endpoint returned `403
   PERMISSION_DENIED: Read access... denied` for an Owner-role account; the
   region-pinned endpoint (`modelarmor.us-central1.rep.googleapis.com`)
   returned the same data successfully. Ask: does the Agent Platform
   console backend that renders the Security tab reliably use the
   region-pinned endpoint for data-residency-compliant templates, or could
   this same endpoint mismatch be silently producing empty reads there
   too?

## What to do on our side regardless

These don't need Google's input — they're actionable now:

- Add an explicit `sanitizeUserPrompt` (or `sanitizeModelResponse`) call in
  `FinancialAdvisorAgentExecutor.execute()` before `runner.run_async`, using
  the `financial-advisor-security` template, so A2A ingress gets a real
  pre-agent check instead of relying entirely on the floor setting.
- Migrate the Model Armor template/floor setting off filter version `v1`
  before it moves to `LEGACY` on **2026-09-01** ([page 5](05-red-team-results.md#cross-cutting-findings-from-the-raw-logs)).
- Decide on the enforcement mode intentionally per environment: keep
  `INSPECT_ONLY` while red-teaming (so Playground stays usable and every
  violation is logged), switch to `INSPECT_AND_BLOCK` for anything
  approaching production traffic.
- Treat `docs/responsible-ai/05-red-team-results.md` as a living regression
  suite: re-run these five prompts after any Model Armor template/floor
  setting change and diff the filter-match results.
