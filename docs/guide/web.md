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
browser stores local Interview records, initial document originals, fixture Blobs, and the display
transcript in IndexedDB. The API receives only the JSON `InterviewState` and the typed response for
the current turn. Original bytes are sent only for text extraction or a package request. Browser
data belongs to the exact web origin, so `http://localhost:5173` and `http://127.0.0.1:5173` have
separate local Interview lists.

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

Use the plus button in the opening message to add documents. Explain their purpose in the same
message when the file name is not sufficient. The browser shows the accepted file types, total size
limit, and reading status. If it cannot read a file, remove the file or keep it without reading.

The wizard can suggest opening documents for a Scenario. Review these files under **Files sent to
your system**. The final package contains only files that a Scenario uses.

The opening screen also offers **Write it yourself** for users who already know the experiment
they want to run. This manual path asks for an experiment ID and description, personas, scenarios,
trial counts, persona references, fixture files, and scorers from the installed scorer catalogue.
The form presents one Experiment editor: set its details first, then add Personas and Scenarios.
A new form starts with empty Persona and Scenario collections. Use the add action in each section
header to create an item. A new Scenario selects all named Personas by default, and a new Persona
is added to existing Scenarios automatically. Each ID and Description is on its own line, and the
entered ID names its item. Select **Done** to close a completed item editor; select **Edit** to open
it again. It creates no Interview and writes no IndexedDB record. The download is the same
`experiment.zip` package as the Interview path. It contains a runnable `experiment.yaml`, the
selected fixture files, and a supporting synthetic `profile.yaml`. Files removed from every
Scenario are deleted from temporary state and are not included in the ZIP.

For this first version, the manual form asks only for what an engine run absolutely needs. The
engine runs from `experiment.yaml`. The fuller `ProductProfile` is used only at report generation,
which reads `inputs/profile.yaml` and is skipped without it. The form therefore synthesizes the
minimum Profile: the default report works, but the product narrative stays yours to write.

Source-code or trace analysis inputs, hosted or cross-device Interview state, authentication,
multi-user access, and evaluation execution remain outside the web client.

When you finish the Interview, the browser client ends and packages it through two API operations.
It first sends the Interview state to `POST /api/v1/wizard/interview/end`, which completes and
validates the specification. It then sends the result to `POST /api/v1/wizard/package`, which
returns one `experiment.zip` package to download. For an Interview that is already complete, the
**Download specification** button packages it through `/package` alone. The ZIP contains
`profile.yaml`, `experiment.yaml`, and a `fixtures/` directory with the validated fixture files
selected during the Interview. The API packages these bytes for one request and retains no fixture
files. Evaluation execution is not a web control in this change.

Future changes must use new API contracts when they are added; do not restore the retired
wizard-owned web server or Python static output.
