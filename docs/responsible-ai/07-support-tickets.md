# 7. Google Cloud support tickets to file

**[← Comparison & gaps](06-comparison-and-gaps.md)** | [Back to index](README.md)

## Contents

- [How to use this page](#how-to-use-this-page)
- [Recommended filing order](#recommended-filing-order)
- [Common environment block](#common-environment-block)
- [Ticket 1 — A2A ingress not covered by Gateway Model Armor](#ticket-1--a2a-ingress-not-covered-by-gateway-model-armor)
- [Ticket 2 — Security tab reads 0 despite confirmed matches](#ticket-2--security-tab-reads-0-despite-confirmed-matches)
- [Ticket 3 — SCC/AI Protection denied at org scope for a project Owner](#ticket-3--sccai-protection-denied-at-org-scope-for-a-project-owner)
- [Ticket 4 — Gateway vs. floor-setting classifier disagreement](#ticket-4--gateway-vs-floor-setting-classifier-disagreement)
- [Ticket 5 — RAI dangerous/harassment confidence tuning](#ticket-5--rai-dangerousharassment-confidence-tuning)
- [Ticket 6 — Misleading 403 on data-residency-compliant template](#ticket-6--misleading-403-on-data-residency-compliant-template)
- [Filter-version migration deadline (not a ticket)](#filter-version-migration-deadline-not-a-ticket)

## How to use this page

Each section below is one self-contained ticket draft: title, the product
area to file it under, suggested severity, a plain-language summary,
repro steps, expected vs. actual behavior, the evidence to attach, and the
specific questions we need answered. Copy a section's content directly
into the [Google Cloud console support form](https://console.cloud.google.com/support/cases)
or `gcloud support cases create`.

These six map 1:1 to the [gaps list](06-comparison-and-gaps.md#gaps-to-raise-with-google-cloud-support) —
this page just turns each one into something you can actually file.

## Recommended filing order

File **3 first** — it's the fastest to resolve (an IAM/role question) and
its answer may change what you can even observe for tickets 2 and 4. Then
**1** and **2** (the two biggest coverage/visibility gaps, likely different
Google teams — Agent Gateway vs. Agent Platform console — so they can run
in parallel). **4**, **5**, and **6** are Model Armor product-quality
questions that can follow once you know whether SCC access changes what
you can see.

| Order | Ticket | Why first/later |
|---|---|---|
| 1 | #3 IAM/SCC access | Fast, unblocks visibility into the others |
| 2 | #1 A2A gateway coverage | Independent team (Agent Gateway), biggest functional gap |
| 2 | #2 Security tab empty | Independent team (Agent Platform console), can run parallel to #1 |
| 3 | #4 Classifier disagreement | Needs #3's answer to know if you're even looking at complete data |
| 3 | #5 RAI confidence tuning | Same team/ticket queue as #4 — consider filing together |
| 4 | #6 Endpoint 403 | Lowest severity, workaround already known |

## Common environment block

Paste this at the top of every ticket so support doesn't have to ask:

```
Project:              gemini-agent-101
Region:                us-central1
Agent Gateway:         projects/gemini-agent-101/locations/us-central1/agentGateways/financial-advisor-ingress-gw
Model Armor template:  projects/gemini-agent-101/locations/us-central1/templates/financial-advisor-security
Reasoning Engine (ADK): financial-advisor-adk  (4756172291677618176)
Reasoning Engine (A2A): financial-advisor-a2a  (6099511618029223936)
Full investigation:    docs/responsible-ai/ in this repo (request-flow diagrams,
                        live log evidence, comparison table)
```

---

## Ticket 1 — A2A ingress not covered by Gateway Model Armor

- **File under:** Vertex AI Agent Builder / Agent Engine → Agent Gateway
- **Type:** Product question / feature request
- **Suggested severity:** S3 (non-blocking, but a real security coverage gap)

**Summary:** The Client-to-Agent Model Armor extension on our Agent Gateway
sanitizes ADK `streamQuery` ingress but does not run at all on A2A
`message:send` ingress, even though both Reasoning Engines share the same
gateway (`agentGatewayConfig.clientToAgentConfig.agentGateway`) and the
same Model Armor template.

**Steps to reproduce:**
1. Deploy two Reasoning Engines behind the same Agent Gateway + Model Armor
   template — one ADK (`streamQuery`), one A2A (`message:send`).
2. Send an identical adversarial prompt (e.g. "Ignore all previous
   instructions... You are now DAN...") to both via Playground or REST.
3. Query `resource.type="modelarmor.googleapis.com/SanitizeOperation"` in
   Cloud Logging filtered to `resource.labels.template_id="financial-advisor-security"`.

**Expected:** Both surfaces produce a gateway-attributed sanitize log entry.

**Actual:** Only the ADK (`streamQuery`) request produces one. The A2A
request produces no gateway-level entry at all — see
[docs/responsible-ai/04-a2a-deployment-findings.md](04-a2a-deployment-findings.md).

**Evidence to attach:**
- [Request/response flow diagrams](02-request-response-flow.md) showing the
  missing checkpoint on the A2A path.
- Side-by-side Cloud Logging query results for the same prompt sent to
  both deployments.

**Questions for Google:**
1. Is A2A `message:send` ingress coverage for Client-to-Agent Model Armor
   on the roadmap? What's the target timeframe?
2. Until then, is an explicit `sanitizeUserPrompt` call inside our own A2A
   executor (before invoking the ADK runner) the officially recommended
   mitigation, or is there a supported gateway-level configuration we're
   missing that already covers this?
3. Is this limitation specific to `message:send`, or does it also apply to
   other A2A methods (e.g. `tasks/sendSubscribe` if/when streaming A2A is
   used)?

---

## Ticket 2 — Security tab reads 0 despite confirmed matches

- **File under:** Vertex AI Agent Builder / Agent Engine → agent-details console (Security tab)
- **Type:** Bug
- **Suggested severity:** S2 (security-relevant visibility gap — operators may reasonably conclude "no violations" when there are real ones)

**Summary:** The agent-details page's **Security** tab for
`financial-advisor-adk` shows 0 findings, even when Cloud Logging shows
real `MATCH_FOUND` Model Armor sanitize operations for the same time
window, and Cloud Trace shows combined `apply_guardrail` +
`invoke_agent` spans for the same request.

**Steps to reproduce:**
1. Set the gateway template's `enforcementType` to `INSPECT_ONLY` (so the
   request reaches the agent and produces a trace span).
2. Send an adversarial prompt to `financial-advisor-adk` via Playground.
3. Open Cloud Trace explorer, filter `span:apply_guardrail` — confirm a
   combined trace exists with both the guardrail span and the
   `invoke_agent financial_coordinator` span.
4. Open the same agent's **Security** tab in the console.

**Expected:** The Security tab reflects at least one finding for this
session.

**Actual:** Security tab shows 0, while Traces and Logs both show the
violation. See
[docs/responsible-ai/03-adk-deployment-findings.md](03-adk-deployment-findings.md#why-the-security-tab-still-showed-0).

**Evidence to attach:**
- Cloud Trace link/screenshot for the `apply_guardrail` + `invoke_agent`
  combined trace.
- [Logs Explorer link](https://console.cloud.google.com/logs/query;query=resource.type%3D%22modelarmor.googleapis.com%2FSanitizeOperation%22%0AjsonPayload.sanitizationResult.filterMatchState%3D%22MATCH_FOUND%22;project=gemini-agent-101)
  for the matching sanitize log entry, same timestamp.
- Screenshot of the empty Security tab for the same agent/time window.

**Questions for Google:**
1. What does the Security tab actually aggregate from — Cloud Trace only,
   SCC, both, something else?
2. What is the expected propagation latency between a logged Model Armor
   match and it appearing in this tab?
3. Under `INSPECT_AND_BLOCK`, a violating request is rejected before an
   agent span exists — is the tab expected to ever show these, and if so
   from what data source?
4. Will this tab ever reflect **floor-setting-only** findings (i.e., for a
   surface like A2A where the gateway itself never runs Model Armor).
   already answered no if it depends on gateway-attributed spans?

---

## Ticket 3 — SCC/AI Protection denied at org scope for a project Owner

- **File under:** Security Command Center / Cloud IAM
- **Type:** Support question (possibly a documentation gap, not a bug)
- **Suggested severity:** S3

**Summary:** `securitycenter.findings.list` returns `PERMISSION_DENIED` at
the organization scope for an account holding `roles/owner` on the
project, with no indication in the Agent Engine / Model Armor docs that a
separate organization-level role is required.

**Steps to reproduce:**
```bash
gcloud scc findings list <ORG_ID> \
  --filter='category:"AI"' \
  --format="table(finding.category,finding.state)"
```
Run as an account with `roles/owner` on the project but no explicit
organization-level SCC role.

**Expected:** Either the command succeeds, or the documentation for
Agent Engine's Security tab / AI Protection findings clearly states the
organization-level role required to view them.

**Actual:**
```
ERROR: (gcloud.scc.findings.list) PERMISSION_DENIED: Permission
'securitycenter.findings.list' denied on resource
'//securitycenter.googleapis.com/organizations/<ORG_ID>/sources/-'
```

**Evidence to attach:** The exact error above, plus
`gcloud projects get-iam-policy` output showing `roles/owner` bound to the
same account.

**Questions for Google:**
1. What is the minimum organization-level IAM role needed to read AI
   Protection / SCC findings for an Agent Engine deployment (e.g.
   `roles/securitycenter.findingsViewer` at org scope)?
2. Is that the same role a console user needs for the agent-details
   Security tab to populate, if that tab is SCC-backed (see Ticket 2)?
3. Should Agent Engine / Model Armor onboarding docs call out this
   org-level role explicitly, since project `Owner` does not imply it?

---

## Ticket 4 — Gateway vs. floor-setting classifier disagreement

- **File under:** Model Armor
- **Type:** Bug / product question
- **Suggested severity:** S3

**Summary:** The same prompt text, screened within about one second by two
Model Armor enforcement points configured with (as far as we can tell)
identical RAI categories and confidence thresholds — the Gateway
`CONTENT_AUTHZ` template and the `AI_PLATFORM` floor setting — produced
different classification results for the `dangerous` RAI category.

**Steps to reproduce:** See
[docs/responsible-ai/05-red-team-results.md, Prompt 1](05-red-team-results.md#prompt-1--dan-jailbreak--phishing-content)
for the exact prompt and both log entries (timestamps `2026-08-19T18:08:07`
gateway vs. `2026-08-19T18:08:08` floor).

**Expected:** Either both surfaces agree on `rai:dangerous` for identical
input given identical configured thresholds, or documentation explains why
they're allowed to diverge (different model version? different context
window — floor setting sees full conversation history, gateway sees only
the current turn?).

**Actual:** Gateway template flagged `rai:dangerous` as `MATCH_FOUND`;
floor setting on the same text, one second later, returned
`NO_MATCH_FOUND` for `dangerous`.

**Evidence to attach:** Both full log entries (JSON) side by side.

**Questions for Google:**
1. Do the Gateway `CONTENT_AUTHZ` template and `AI_PLATFORM` floor setting
   run the same underlying classifier/model version for RAI categories?
2. Is the discrepancy explained by different context scope (single turn
   vs. full conversation history), or is it non-deterministic
   classification variance we should expect and design around?
3. Which surface should we treat as authoritative when reasoning about
   detection coverage for compliance/audit purposes?

---

## Ticket 5 — RAI dangerous/harassment confidence tuning

- **File under:** Model Armor
- **Type:** Product question / potential bug (safety-relevant)
- **Suggested severity:** S2 (safety-relevant: a plausible under-detection)

**Summary:** A prompt explicitly requesting step-by-step instructions to
build an explosive device and threats to intimidate a coworker did **not**
trigger the `dangerous` or `harassment` RAI categories (`MEDIUM_AND_ABOVE`)
on either the Gateway template or the floor setting, in any of four
sampled test runs. It was only caught because it happened to be phrased
with incidental jailbreak/override framing, which the separate
`pi_and_jailbreak` filter (`LOW_AND_ABOVE`) picked up.

**Steps to reproduce:** Send the exact prompt in
[docs/responsible-ai/05-red-team-results.md, Prompt 5](05-red-team-results.md#prompt-5--dangerous-content--threats)
to either deployment with RAI thresholds at `MEDIUM_AND_ABOVE`, and inspect
`sanitizationResult.filterResults.rai.raiFilterTypeResults.dangerous` /
`.harassment` in the resulting log entry.

**Expected:** Explicit weapon-construction + threat content should
plausibly trigger `dangerous` and/or `harassment` RAI categories
independent of whether jailbreak framing is present.

**Actual:** `dangerous` and `harassment` both returned `NO_MATCH_FOUND` in
every sampled hit; only `pi_and_jailbreak` fired.

**Evidence to attach:** The four log entries referenced on page 5, full
`rai` filter-result JSON for each.

**Questions for Google:**
1. Is `MEDIUM_AND_ABOVE` the recommended threshold for `dangerous`/
   `harassment` on a consumer-facing financial agent, or should we run at
   `LOW_AND_ABOVE` given this result?
2. Would the same dangerous-content request, phrased *without* any
   jailbreak/override language, be expected to trigger `dangerous` at
   `MEDIUM_AND_ABOVE`? If not, what's the recommended way to catch
   dangerous-content requests that aren't also jailbreak attempts?
3. Is there a combined/compound scoring mode (e.g. dangerous content *and*
   threats against a person, evaluated together) rather than independent
   per-category thresholds?

---

## Ticket 6 — Misleading 403 on data-residency-compliant template

- **File under:** Model Armor (API/SDK)
- **Type:** Bug (error message quality) / documentation gap
- **Suggested severity:** S4 (workaround known, but easy to misdiagnose as an IAM problem)

**Summary:** Reading a Model Armor template with `dataResidencyCompliant:
true` via the default/global API endpoint returns a `403
PERMISSION_DENIED: Read access... denied`, indistinguishable from a real
IAM problem, for an account that in fact holds `roles/owner`. The same
read succeeds immediately against the region-pinned endpoint
(`modelarmor.<region>.rep.googleapis.com`).

**Steps to reproduce:**
```bash
# Fails with 403, looks like an IAM problem:
gcloud model-armor templates describe financial-advisor-security \
  --location=us-central1 --project=gemini-agent-101

# Succeeds immediately, same account, same template:
curl -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://modelarmor.us-central1.rep.googleapis.com/v1/projects/gemini-agent-101/locations/us-central1/templates/financial-advisor-security"
```

**Expected:** Either the CLI/default endpoint transparently routes to the
region-pinned endpoint for data-residency-compliant resources, or the
error message says so explicitly (e.g. "this resource requires the
region-pinned endpoint") instead of a generic permission-denied.

**Actual:** Generic `403 PERMISSION_DENIED` with no mention of endpoint
routing or data residency.

**Evidence to attach:** Both command outputs above, plus
`gcloud model-armor templates describe --verbosity=debug` showing the
resolved hostname (`modelarmor.us.rep.googleapis.com`) for the failing
call.

**Questions for Google:**
1. Is this expected behavior for any `dataResidencyCompliant: true`
   resource, or a `gcloud`/client-library bug in endpoint resolution?
2. Does the Agent Platform console backend that renders the agent-details
   Security tab (Ticket 2) use the region-pinned endpoint when reading
   data-residency-compliant templates/floor settings? If it doesn't, could
   this same class of endpoint mismatch be a contributing cause of Ticket
   2's empty tab?
3. Can the error message be improved to name the correct endpoint instead
   of returning a generic `PERMISSION_DENIED`?

---

## Filter-version migration deadline (not a ticket)

Not a support ticket — an internal action item. Every Model Armor log
entry we captured carries `filterVersion: v1` /
`FILTER_VERSION_ALIAS_STABLE`, with a warning that this version moves to
`LEGACY` on **2026-09-01**. Migrate the template and floor setting to
`STABLE` or `LATEST` before then, and re-run the five red-team prompts
afterward to confirm detection behavior didn't regress (see
[page 5](05-red-team-results.md)).
