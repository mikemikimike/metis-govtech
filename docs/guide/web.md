# METIS web client

`apps/web` is a browser client for the stateless `metis-api` service. The normal local run uses
one active environment file and two terminals. From the repository root, create the local file
once:

```bash
cp apps/api/.env.example .env
```

Set `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `INTERVIEW_MODEL` in that file. The API uses the same
provider names as the wizard. `JUDGE_MODEL` and `USER_AGENT_MODEL` are engine settings and are not
used by the API.

```bash
make install          # install everything

make install-api      # install only API dependencies
make install-web      # install only web dependencies
```

Then start the processes:

```bash
# terminal 1
make run-api

# terminal 2
make run-web
```

Set `METIS_API_ORIGIN` when the API uses another origin. Vite proxies `/api` to that origin. The
browser stores local Interview records, fixture Blobs, and the display transcript in IndexedDB. The
API receives only the JSON `InterviewState` and the typed response for the current turn. Fixture
bytes are sent only when the user requests a package. Browser data belongs to the exact web origin,
so `http://localhost:5173` and `http://127.0.0.1:5173` have separate local Interview lists.

The package-level `.env.example` files are entry-point templates. They do not require three active
`.env` files. One root `.env` can contain the union of settings needed by the commands you run.

Use `make check-web` for non-mutating web checks. Use `make build-web` when you need the production
Vite output. The web requests metric summaries only after a Profile contains a Criterion, and a
failed metric request does not block the Interview.

The web gets its opening question, busy message, perspective labels and questions, and the grouped
ARC capability catalogue from `GET /api/v1/wizard/config`. The wizard package owns these values in
`packages/wizard/src/metis/wizard/config.yaml` and
`packages/wizard/src/metis/wizard/capabilities.yaml`. The perspective prompt content is separate,
editable files in `packages/wizard/src/metis/wizard/application/perspectives/`.

The opening flow first shows the product question and composer. Four full-width perspective choices
follow under **Who is this evaluation for?** Each choice shows its configured question on hover and
keyboard focus. Continue then shows the capability catalogue and confidence choice without calling
the API. Capability descriptions also appear on hover and keyboard focus. The capability list can
be empty. Confidence is required and answers how complete the selection is, so the screen does not
preselect Low, Medium, or High. The catalogue keeps its three configured groups and does not change
when the perspective changes. **Start interview** sends all opening values in one request.

The browser sends one start request:

```json
{
  "description": "A research assistant",
  "known_capability_ids": ["internet_search_access"],
  "capability_confidence": "medium",
  "perspective": "end_user"
}
```

The response state carries the opening values at `context.capability_evidence`. The browser keeps
that state and sends it unchanged on later turns. Capability evidence is not written into the
Profile or the finished specification.

The web client does not provide these features yet:

- direct Profile or experiment authoring outside the wizard conversation;
- source-code or trace analysis inputs;
- hosted or cross-device Interview state;
- authentication and multi-user access;
- evaluation execution.

When you finish the Interview, the browser client ends and packages it through two API operations.
It first sends the Interview state to `POST /api/v1/wizard/interview/end`, which completes and
validates the specification. It then sends the result to `POST /api/v1/wizard/package`, which
returns one `experiment.zip` package to download. For an Interview that is already complete, the
**Download specification** button packages it through `/package` alone. The ZIP contains
`profile.yaml`, `experiment.yaml`, and a `fixtures/` directory with the validated fixture files
selected during the Interview. The API packages these bytes for one request and retains no fixture
files. Evaluation execution is not a web control in this change.

These are deferred changes. They must use new API contracts when they are added; do not restore the
retired wizard-owned web server or Python static output.
