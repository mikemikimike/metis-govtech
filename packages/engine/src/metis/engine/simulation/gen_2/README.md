# gen_2: the generic HTTP runner

For people working on METIS and early testers. `gen_2` is the second generation of the
simulation: a user agent decides one plain-language action per turn, and a runner carries
it out on the target. The generic HTTP runner lets you bind an app that has an OpenAPI
specification with a YAML file, a *target binding*, instead of writing a Python runner.

> **Tested on Orca's API only.** The runner has run Orca's REST API and nothing else. The
> rules below were each found on Orca, and a second app will probably need more. Once a
> second app has been bound, this page becomes the basis for the user guide.

## How a turn works

```
user agent ──action──▶ HttpRunner.act ──▶ runner agent (LLM) ──tool calls──▶ target
 "Ask ⟦hi⟧"               │                    │                             │
                          │                    └── http_request, poll_until, fetch_files,
                          │                        session_id_from, note, report
                          ▼
                    Observation  ◀── built by code from what the transport log recorded
```

1. The user agent writes one action. Text meant for the target sits between `⟦` and `⟧`.
2. `act` numbers those spans `{{1}}`, `{{2}}`, ... and settles any submission left open by
   an earlier action.
3. The runner agent, an LLM, is shown an index of the target's OpenAPI specification
   (fetched once per trial), reads an endpoint's definition with `operation` when it needs
   it, and calls tools until it calls `report`. Results from earlier rounds are shortened
   to the log entry that holds them. It is limited to 12 rounds and to
   `response_wait_ms` plus 60 seconds, and never goes past the trial deadline.
4. Code builds the `Observation`. The agent's own words fill only `reading`
   (`outcome`, `why`, `next_options`), which the user agent is told is an interpretation.

Every request and response goes to `outputs/trials/<id>/evidence/log.jsonl`, and every LLM
call to `evidence/llm_calls.jsonl`.

## The rules code enforces, and why

Each rule answers something an LLM did that looked reasonable and was wrong. Code
enforces them; the prompt only explains them.

| Rule | Why |
| --- | --- |
| A path is absolute, as the specification writes it, with no `//`, `..`, `?` or `#`. | A path can otherwise leave the API or smuggle a query. |
| `forbidden_calls` in the binding are refused before anything is sent. | The agent chose a plausible call, such as a delete, that the owner never wants made. |
| The agent cannot set `Authorization`, `Cookie` or `Host`. Code adds credentials. | The agent must never see or send a secret, and the log redacts them. |
| The user's words reach the target only as `{{n}}` placeholders that code replaces. | The record can then say the target received the user's words exactly. |
| A submission is refused when the action quoted nothing. | The agent invented a message the user never wrote. |
| One submission may be open at a time; `poll_until` settles it. | A second message sent while the first is running corrupts the conversation. |
| The session ID is copied from a submission's reply, and nowhere else. | The agent once pointed at an upload's file ID. |
| `fetch_files` takes a logged listing that is this conversation's, at most 100 files, and one `{id}` in the path. It skips the user's own uploads and files already held. | An account-wide listing would pull in files from other conversations. |
| A reply or promised file may be cited only from entries logged during this action. | An earlier action's reply would otherwise be reported as this one's. |
| A promised name must be a single line. | A whole page of text is not a file name. |
| A 429 is waited out (up to 3 resends, honouring `Retry-After`) while the trial has time. | Rate limits are the target's, not a failure. |

A refusal goes back to the agent as `{"error": "refused, nothing was sent: ..."}`, so it
can try something else. Nothing here raises for the agent's mistakes.

`observed` is `False` when a submission is still open or a call failed at the transport.
`notice` carries a problem METIS itself found: a poll the target answered with a 4xx, an
open submission, a transport failure, the time limit or the round cap.

## Writing a target binding for a new app

The binding is a YAML file inside the experiment's `inputs/` folder, named from
`specification.yaml`:

```yaml
runner_factory_ref: metis.engine.simulation.gen_2.runners.http.HttpRunnerFactory
target_binding: targets/my-app.yaml
```

Its shape is `TargetBinding` in `metis.core.target_binding`, published as
`packages/core/schemas/target-binding.schema.json`. Start from the Orca example below and
change these:

- `identity` names the app.
- `spec_url` is where the OpenAPI document lives. `${NAME}` is read from the environment.
  The runner joins each path to the specification's first server URL, so patterns and
  paths are written *relative to that server*: a chat call is `/chat`, not `/api/v1/chat`.
- `auth.secret_env` names the environment variable holding the credential, sent as the
  scheme the specification declares. Secrets are never written in the file.
- `secret_headers` adds a header from an environment variable to matching calls. A secret
  that is not set adds nothing.
- `submissions` lists the calls that send the user's message. Left empty, any `POST`,
  `PUT` or `PATCH` with a JSON body counts.
- `forbidden_calls` are `METHOD /glob` patterns; `*` matches within a path segment and
  `**` across segments. Write `*` for a path parameter.
- `advice` (`limits`, `notes`) is for the agent only. Code does not check it. Put in it
  what the specification cannot say, such as "the first chat call starts the session".

The example, `packages/engine/example-experiment/targets/orca-api.yaml`:

```yaml
# yaml-language-server: $schema=../../../core/schemas/target-binding.schema.json
# Orca's REST API, bound to the generic HTTP runner. Paths here are the ones the
# specification writes, relative to its server URL (/api/v1), so a chat call is /chat.
schema_version: 1
identity: {name: Orca, version: "1.0.0"}
transport: http
spec_url: ${ORCA_API_URL}/openapi.json  # ORCA_API_URL ends in /api/v1
tls_verify: false  # Orca's host uses a self-signed certificate
auth: {scheme: from_spec, secret_env: ORCA_API_KEY}
secret_headers:
  # Optional: bills every chat turn to your own platform project on a fixed model.
  - {match: "POST /chat", header: X-PlatformAI-Key, env: ORCA_PLATFORM_AI_KEY}
forbidden_calls:
  - "DELETE /**"
  - "POST /chat/cancel"
advice:
  limits:
    submit_per_minute: 6
    read_per_minute: 120
    note: Over a limit is a 429 with Retry-After; code waits and resends. Poll every few seconds.
  notes: |
    The first POST /chat without a sessionId starts the session; never call POST /sessions.
    Upload a file with POST /files first, then list its fileId in the chat turn's files.
```

To try a binding, set the variables it names and run the experiment as usual. The runner
agent uses `RUNNER_AGENT_MODEL` (falling back to `USER_AGENT_MODEL`) with the same
`OPENAI_API_KEY` and `OPENAI_BASE_URL` as the user agent.

## Not covered yet

Trimming what is resent to the LLM each round (#482). The closing step that collects files
after the conversation, and the record checks (#483); `end_chat` does nothing until then.
Whether the quoted text reached the target word for word is not measured yet; `Spans.sent`
keeps the data for those checks.
