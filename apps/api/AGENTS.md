# metis-api

See root [AGENTS.md](../../AGENTS.md) for monorepo-wide instructions.

IMPORTANT: Always talk in ASD-STE100 Simplified Technical English.

## Package Purpose

A thin, stateless HTTP door over the wizard's public Interview interface. It translates request and
response JSON and status codes and holds no user state. Every interview rule stays inside
metis-wizard; this package must not learn any of them.

## The client-held state boundary

The service keeps only immutable settings and model clients for the process lifetime. It keeps no
Profile, pending request, or Interview state — each lifecycle operation carries the required state
in the request body and the next state goes back whole in the response. Any instance can therefore
serve any operation, and no Interview file is ever written. Do not add per-user server state; if an
operation needs to remember
something, it belongs in the returned `InterviewState`, not on the app.

## Module layout

```
src/metis/api/
├── main.py            the app composition root: /health, the wizard router, the error handlers
├── routes/wizard.py   Interview start, turn, end, and compile routes — status mapping only
├── settings.py        environment-backed settings and the production dependency composition
├── cli.py             the `metis-api` executable (Uvicorn on metis.api.main:app)
└── __init__.py        version and the re-exported core version
```

The dependency arrow is `apps/api -> metis.wizard`. The router calls `handle_interview` and
`compile_profile` from the `metis.wizard` facade and maps the typed result onto an HTTP status
(200/400/422/503/500) in one error shape. No stage, Profile, prompt, matching, or compilation rule
lives here.

## Testing

API tests are door tests: they prove the HTTP adapter preserves wizard behaviour, not the wizard
rules themselves. They reuse the wizard's own offline corridor — the `ScriptedInterviewer`, the
`walk` driver, and the hand-authored profiles under `packages/wizard/tests/fixtures/` — through the
`send` transport, so the door and the wizard's Slice B gate share one answer script. `conftest.py`
puts that fixture tree on `sys.path` and injects the scripted dependency pair, so no test builds the
real gateway or reaches the network.

Cover the door contract with representative cases: status mapping, the stable failure body,
statelessness across two app instances, the generated OpenAPI discriminators, and one offline
Interview start/turn/end-to-`/compile` end-to-end validated through the engine gate. Do not repeat every driver
example.

## Package-Specific Notes

- Settings map the service names `API_KEY`, `BASE_URL`, and `JUDGE_MODEL` onto the gateway's own
  `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `INTERVIEW_MODEL` variables in `settings.py`.
- Build the image from the repository root: `docker build -f apps/api/Dockerfile -t metis-api .`.
  METIS is one uv workspace with a single lockfile, so the build needs the workspace root and the
  path-dependency members.
