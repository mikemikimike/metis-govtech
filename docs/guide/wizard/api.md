# Use the Wizard HTTP API

The Wizard API runs the same Interview as the [web client](web.md). Use it to add evaluation
planning to another application or workflow. See the [Wizard overview](../wizard.md) for the
evaluation terms.

All routes start with `/api/v1/wizard`. Open `http://localhost:8001/docs` for the complete OpenAPI
schemas and named examples.

## Before you start

Install and start the API from the repository root:

```bash
make install-api
cp apps/api/.env.example .env
make run-api
```

Set `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `INTERVIEW_MODEL` in `.env`. The examples use
`http://localhost:8001` and require `curl` and `jq`.

The API is stateless. Your client owns the Interview state.

| Client rule | Required action |
|---|---|
| Save progress | Save the complete `state` from each successful lifecycle response. |
| Send progress | Send that state unchanged with the next `/turn` or `/end` request. |
| Read progress | Check `outcome` after every `/start`, `/turn`, or `/end` response. |
| Prevent stale answers | Use the `request_id` from the latest `state.pending` screen. |
| Keep files | Store original documents until packaging is complete. State contains no file bytes. |

The examples keep the latest successful response in `interview.json`. This is the only saved
Interview file.

```text
config and optional document extraction
                    │
                    ▼
                  start
                    │
                    ▼
                  turn ◄──────────────────────┐
                    │                         │
                    ├─ awaiting_response ─────┘
                    ├─ done ────────────────► compile or package
                    └─ optional end ─────────► awaiting_response or done
```

### Read client configuration

`GET /config` returns the opening copy, Perspectives, ARC capabilities, and document limits.

```bash
curl --fail-with-body http://localhost:8001/api/v1/wizard/config
```

Use the returned IDs in the start request. An empty capability selection is valid.

### Extract document text

`POST /documents/extract` is optional. Call it before `/interview/start`.

```bash
curl --fail-with-body http://localhost:8001/api/v1/wizard/documents/extract \
  -F 'files=@policy.pdf'
```

The response contains a `documents` list with canonical file names and extracted text. The route
supports UTF-8 TXT, Markdown, YAML, JSON, CSV, PDF text layers, and DOCX files. It does not run OCR. Add the returned
list to the start request. The opening document list cannot change after start.

Keep each original file. If a Scenario uses it, send the original bytes to `/package`.

## Start an Interview

`POST /interview/start` creates the first state and pending screen.

| Request field | Required | Description |
|---|---|---|
| `description` | Yes | Description of the target. |
| `known_capability_ids` | Yes | Capability IDs from `/config`. The list can be empty. |
| `capability_confidence` | Yes | `low`, `medium`, or `high`. |
| `perspective` | No | Defaults to `end_user`; other values come from `/config`. |
| `documents` | No | Output from `/documents/extract`, or document names without text. |

Example request:

```json
{
  "description": "A research assistant that answers policy questions and cites its sources.",
  "perspective": "end_user",
  "known_capability_ids": [],
  "capability_confidence": "low",
  "documents": []
}
```

A successful response contains these control fields:

| Response field | Description |
|---|---|
| `type` | `success`. |
| `state` | Complete client-held Interview state. |
| `state.pending` | The screen that needs an answer. |
| `stage` | Current Interview stage. |
| `missing` | Structured gaps that stop completion. |
| `outcome` | `awaiting_response` or `done`. |

Save the successful response as `interview.json`:

```bash
if response=$(curl --fail-with-body http://localhost:8001/api/v1/wizard/interview/start \
  -H 'Content-Type: application/json' \
  --data '{
    "description": "A research assistant that answers policy questions and cites its sources.",
    "perspective": "end_user",
    "known_capability_ids": [],
    "capability_confidence": "low"
  }') &&
  printf '%s\n' "$response" | jq -e '.type == "success"' > /dev/null; then
  printf '%s\n' "$response" > interview.json
else
  printf '%s\n' "$response"
fi
```

Do not rebuild state from the visible Specification or from an abbreviated response example.

## Answer a turn

`POST /interview/turn` answers `state.pending`. Repeat it while `outcome` is
`awaiting_response`.

| Request field | Description |
|---|---|
| `state` | Complete `state` from `interview.json`. |
| `request_id` | Exact ID from `state.pending.request_id`. |
| `response` | Typed answer that matches `state.pending.type`. |

Read the next screen with:

```bash
jq '{outcome, pending: .state.pending}' interview.json
```

### Chat

For `pending.type: "chat"`, send text:

```json
{
  "type": "chat",
  "text": "Policy analysts use it to compare new guidance with existing policy."
}
```

### Choice

For `pending.type: "choice"`, send offered option IDs:

```json
{
  "type": "choice",
  "selected": ["continue"]
}
```

Options can occur in `pending.options`, warnings, cards, or card components. Form an option ID by
joining its non-empty `action`, `target`, and `via` values with colons. For example,
`{"action":"cover","target":"S-1","via":"EB-2"}` becomes `cover:S-1:EB-2`.

Send only enabled options from the current screen. Multiple selections are valid when
`pending.multi` is true.

Choice screens can also contain number or file-list fields. Use the field ID as a key in `values`:

```json
{
  "type": "choice",
  "values": {
    "trials:S-1": 5,
    "files:S-1": ["policy.pdf"]
  }
}
```

### Form

For `pending.type: "form"`, use the exact field IDs from `pending.fields`:

```json
{
  "type": "form",
  "values": {
    "target_name": "Policy assistant"
  }
}
```

### Submit the turn

Set `answer` to one of the response objects above. Build the turn request from
`interview.json`, then save the successful result back to the same file:

```bash
answer='{"type":"chat","text":"Policy analysts compare new guidance."}'
request=$(jq -c --argjson answer "$answer" \
  '{state: .state, request_id: .state.pending.request_id, response: $answer}' \
  interview.json)

if response=$(curl --fail-with-body http://localhost:8001/api/v1/wizard/interview/turn \
  -H 'Content-Type: application/json' \
  --data-binary "$request") &&
  printf '%s\n' "$response" | jq -e '.type == "success"' > /dev/null; then
  printf '%s\n' "$response" > interview.json
else
  printf '%s\n' "$response"
fi
```

Read the new pending screen before the next answer. The request ID, response type, and offered
options can change after every turn.

## Finish and create the output

A normal final `/interview/turn` can return `outcome: "done"`. You can then compile or package the
Specification.

### Finish early

`POST /interview/end` asks the Wizard to complete the remaining work and validate the Specification. It
is optional.

Send the complete saved state from `interview.json`, then save the successful result back to the
same file:

```bash
request=$(jq -c '{state: .state}' interview.json)

if response=$(curl --fail-with-body http://localhost:8001/api/v1/wizard/interview/end \
  -H 'Content-Type: application/json' \
  --data-binary "$request") &&
  printf '%s\n' "$response" | jq -e '.type == "success"' > /dev/null; then
  printf '%s\n' "$response" > interview.json
else
  printf '%s\n' "$response"
fi
```

A successful response has two possible outcomes:

| Outcome | Next action |
|---|---|
| `awaiting_response` | Save the returned state and continue with `/interview/turn`. |
| `done` | Compile `state.specification` or package the full `state`. |

HTTP 200 confirms that the operation succeeded. Check `outcome` to learn whether the Interview is
complete. If the Wizard cannot complete the Interview, the API returns HTTP 400 with the code
`completion_failed`. See [Handle errors and resume](#handle-errors-and-resume).

### Compile or package

Use either endpoint after `/turn` or `/end` returns `done`.

| Endpoint | Input | Output | Use |
|---|---|---|---|
| `POST /compile` | `state.specification` as JSON | `specification.yaml` as a string and `specification` with assigned Task IDs | Store or display YAML yourself. |
| `POST /package` | One JSON form field: `state` for Interviews or `specification` for manual exports; fixture file parts | `YYYYMMDD-HHMMSS-interview.zip` | Download a portable specification. |

Compile directly from `interview.json`:

```bash
jq '.state.specification' interview.json | \
  curl --fail-with-body http://localhost:8001/api/v1/wizard/compile \
    -H 'Content-Type: application/json' \
    --data-binary @-
```

Package directly from `interview.json`:

```bash
jq -c '.state' interview.json | \
  curl --fail-with-body http://localhost:8001/api/v1/wizard/package \
    -F 'state=<-' \
    --remote-name --remote-header-name
```

Add one `-F 'files=@<path>'` part for each original fixture referenced by the completed Specification.
The response `Content-Disposition` header supplies the ZIP filename. The ZIP contains a
`YYYYMMDD-HHMMSS-interview/` root folder with `inputs/interview_state.json`, `outputs/specification.yaml`, and
`outputs/fixtures/`. The API compiles the Specification directly from the supplied state and
saves that same state with its current JSON format. Send exactly one source field; requests
with both `state` and `specification` are rejected.

For a manual export, send the user-authored Specification in the `specification` form field.
The manual ZIP uses `YYYYMMDD-HHMMSS-manual.zip` and a matching root folder. It contains an
empty `inputs/` folder and the same `outputs/` layout.

The API retains no uploaded bytes or experiment files. A successful package response contains
a generated Specification and marks a completed export. Extract the archive into `experiments/design/`
and use its dated folder as the Engine input. For example, run
`metis engine run --input-dir experiments/design/20261016-223045-interview/outputs/`. Task fixture references stay relative
to `outputs/fixtures/`. Wizard exports contain no Testbed embedding caches or score files.

## Handle errors and resume

All failures contain `type`, `code`, `message`, and `retryable`. Interview failures can also contain
a safe `state` and `missing` entries.

| HTTP status | Code | Client action |
|---|---|---|
| 400 | `request_id_mismatch` | Reload the latest pending screen and prepare its answer again. |
| 400 | `response_type_mismatch`, `response_not_offered` | Match the current screen type and offered IDs. |
| 400 | `no_pending_request` | Check `outcome`; a complete Interview can be compiled or packaged. |
| 400 or 422 | `validation_error` | Correct the request fields or types. |
| 400 | `completion_failed` | Read `missing` and continue the Interview. |
| 400 | `compilation_failed` | Supply a runnable Specification and all referenced fixture files. |
| 400 | Document error codes | Correct the file type, content, count, or size using limits from `/config`. |
| 503 | `model_unavailable` | Keep saved state and retry when `retryable` is true. |
| 500 | `internal_error` | Keep saved state and inspect the API logs. |

Write only successful lifecycle responses to `interview.json`. If a request fails, keep the last
successful file. Use a returned safe state to prepare the corrected request.

To resume, load `interview.json`, check `outcome`, and read `state.pending`. The API needs no
server-side Interview ID. Process one request at a time. Keep a separate display transcript when
you need the complete conversation; Interview state contains only recent history.

Keep the `specification` returned by `/compile` when the request contains new Tasks
with blank IDs. Submit that Specification on later edits and to `/package`. Task IDs
are assigned by the backend. Keep them when editing a Task. Copying a Task requires a
new ID. `specification.yaml` is the only YAML file in the archive.
