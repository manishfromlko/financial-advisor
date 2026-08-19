# Agent Registry Notes

## Is Agent Registry mandatory for A2A agents?

No. An A2A agent does not need an Agent Registry entry to run.

An A2A agent deployed on Agent Engine can be invoked directly using its authenticated endpoint, for example:
- `.../reasoningEngines/{ENGINE_ID}/a2a/v1/card`
- `.../reasoningEngines/{ENGINE_ID}/a2a/v1/message:send`

If you access the card URL in a browser without authentication, you will get `401 UNAUTHENTICATED`.
This is expected because the endpoint requires OAuth credentials.

## When should you use Agent Registry?

Use Agent Registry when you need:
- Central discovery of agents across teams
- Governance (ownership, review, lifecycle, and deprecation tracking)
- Standardized metadata for discoverability
- Controlled sharing and access at organization scale
- Enterprise publishing and catalog workflows

## What agents are usually registered?

Commonly registered:
- Production agents used by multiple teams
- Reusable domain agents (for example: finance, risk, support, data)
- Stable A2A agents with clear skills and interface contracts
- Strategic ADK or non-A2A agents that should be discoverable in a shared catalog

Commonly not registered:
- Local development agents
- One-off experiments and prototypes
- Internal wrappers only used by a single private workflow

## Practical rule of thumb

Register an agent if discoverability and governance matter.
Skip registration when invocation is direct, tightly scoped, and controlled by a small set of callers.

## Notes for this repository

- This repo has an A2A wrapper (`financial-advisor-a2a`) that is discoverable via its Agent Engine A2A endpoints.
- Registry entry is optional unless your organization requires centralized cataloging and governance.
- Authentication is required to access the A2A card endpoint.
