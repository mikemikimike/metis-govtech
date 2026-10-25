# Use the Wizard in a browser

Use the web client to run a guided Interview in your browser and download the specification for
the Engine.

- The web client uses the Wizard API to process answers and build the download. The
  [API guide](api.md) shows how to use the same features in your own client.
- The browser stores Interview records, original documents, fixture files, and the display
  transcript in its IndexedDB database.

See the [Wizard overview](../wizard.md) for the shared Interview flow and output concepts.

## Start the web client

1. From the repository root, copy the API environment template:

   ```bash
   cp apps/api/.env.example .env
   ```

2. Set `OPENAI_API_KEY`, and `OPENAI_BASE_URL` when you do not use the default OpenAI endpoint.
   `INTERVIEW_MODEL` and `EMBEDDING_MODEL` are optional. The API starts when a setting is missing.
   Without an interview key, Send is grey and shows "Configure API keys to start interview".
   Without an embeddings key, a banner says "Set up embedding models to select optimal graders",
   and the Interview still runs. See the [model guide](../models.md).
3. Install the full workspace, or install the API and web projects separately:

   ```bash
   make install
   # or
   make install-api
   make install-web
   ```

4. Start the API server and the web development server in two terminals:

   ```bash
   # terminal 1
   make run-api

   # terminal 2
   make run-web
   ```

The API runs at `http://localhost:8001` by default. If the API uses another address, set
`METIS_API_ORIGIN` before you start the web development server. The web development server
forwards `/api` requests to that address.

## Start a guided Interview

The opening box holds all of the setup. Its bottom row has the documents button, the Perspective
control, and **Capabilities**.

1. Enter a description of the target.
2. Select who the evaluation is for. The Perspective control shows the current Perspective. End
   user is the default, and the control marks it until you open the control. The panel under the
   box shows the guiding question of each Perspective.
3. Optional: select **Capabilities**. The ARC capabilities show in three columns, one for each
   group. Select each capability that you know the target has. On a small screen, the
   capabilities open in a full-width sheet.
4. Optional: under **Confidence**, select Low, Medium, or High. The value states how complete the
   selection is. With no confidence, the Wizard uses Low, because the selection may be
   incomplete.
5. Select Send, or press Enter. This sends all opening values in one request.

The web client gets the opening text, Perspectives, capability catalogue, and document limits from
the API. It keeps the returned Interview state and sends the whole state with each answer. The API
does not save the state.

## Go back to an earlier step

Each review step after Clarify shows **← Back**. Back opens the step before it with its current
content.

- Back from Behaviours shows a form with the Target name, users, description, and detail. A
  required field that you leave empty keeps its current value.
- Continue with no change returns to the later step. The Wizard drafts nothing again.
- If you change content that later content came from, the Wizard asks what to do with the later
  content. You can keep it, regenerate it, or review it yourself.

Clarify has no Back, because it is the first step. To correct the description, say so in your
answer, for example "The target is for staff only." To change the Perspective, capabilities, or
documents, select **New evaluation**. The earlier Interview stays in History.

## Review Criteria

Expand **Grader details** to inspect the settings, or select **Edit assessment** to change them.
See [Review and edit Criteria](../wizard.md#review-and-edit-criteria).

## Add documents

1. Select the plus button in the opening message.
2. If a file name does not make the purpose of a document clear, explain it in the same message.
3. Check the reading status of each file. Remove an unreadable file, or keep it without extracted
   text.

Document facts:

- The browser shows the accepted file types and size limits.
- The API extracts text from UTF-8 TXT, Markdown, YAML, JSON, CSV, PDF text layers, and DOCX files.
- The API does not run OCR. Scanned PDFs give no text.
- The Wizard can suggest an opening document as a Test Case fixture. Review each suggestion under
  **Files sent to your target**.
- The final package contains only files that a Test Case uses.

## Finish and download

1. Answer each Interview screen.
2. Review the final Personas, Scenarios, and Test Cases.
3. Select **Continue** on the final review screen to complete the Interview.
4. On the **Run settings** step, type the user agent, runner agent, and judge model names, or leave
   a field empty to use the environment. These models affect scores, so the specification records
   them. The step takes model names only. Keys stay in `.env`. See the
   [model guide](../models.md).
5. Select **Continue and download**. The browser downloads `YYYYMMDD-HHMMSS-interview.zip`, with
   the models that you set. If you change no field, the download is the same as without the step.

To download the specification again later, select **Download specification** in the document pane.

To finish early, select **Skip interview and download specification**. The Wizard checks whether
the specification is ready. It can ask for more information or a document review before it
completes the Interview. Then the **Run settings** step comes before the download.

The archive contains:

```text
YYYYMMDD-HHMMSS-interview/
├── inputs/
│   └── interview_state.json
└── outputs/
    ├── specification.yaml
    └── fixtures/
```

The API compiles the Specification from the same final Interview state that it saves in the
archive. This state keeps document names, extracted text, and limited recent history. The full
display transcript stays in browser storage.

Extract the archive into `experiments/design/`. For an Interview exported on 2026-10-16 at 22:30:45, run:

```bash
metis engine run --input-dir experiments/design/20261016-223045-interview/outputs/
```

The browser sends only the original fixture files that the current Tasks use. The API builds
the archive for that request and does not keep the files.

## Write the Experiment directly

Use **Write it yourself** when you already know the Experiment to run. This path does not use the
Interview and creates no Interview record.

1. Select **Write it yourself**.
2. Set the Experiment ID and description.
3. Define Personas and Scenarios in their sections.
4. Select **Add test case**. Select one Persona and one Scenario,
   and set its Trial count, scorers, and files. Add more test cases as needed.
5. Select **Download specification**.

If a field is not complete, the download does not start. The form shows "Some fields are not
complete.", marks each field that needs a change in red, and moves the focus to the first one.
Each marked field tells you what to change. Every Scenario must be selected in at least one
test case.

Editor rules:

- Select **Done** to close a Persona editor. Select **Edit** to open it again.
- Each test case selects exactly one Persona and one Scenario.
- Multiple test cases can use the same pair with different settings or files.
- Renaming a Persona or Scenario updates its test case references. Removing one
  clears those selections. Select a replacement before you download.
- Each Scenario needs at least one test case.

The manual export uses `YYYYMMDD-HHMMSS-manual.zip` and a matching root folder. It contains an empty `inputs/` folder, `outputs/specification.yaml`, and the
selected files under `outputs/fixtures/`. It contains no Interview state.

## Browser storage and current limits

- Unsent drafts are lost on refresh or page closure.
- Edit each Interview in one tab at a time.
- Failed or interrupted replies require a manual retry. Use **Edit reply** to correct the input.
- Browser data belongs to the exact web origin. For example, `http://localhost:5173` and
  `http://127.0.0.1:5173` have separate Interview lists.
- The web client does not provide:
  - hosted or cross-device Interview storage;
  - authentication or multi-user access;
  - source-code or trace analysis; or
  - evaluation execution.

## Development checks

- `make check-web` runs the web checks.
- `make build-web` makes a production build.

Scorer settings in the manual form accept a JSON object. The downloaded document
stores these settings on Criteria. Each test case becomes one Task in the YAML. The form retains Task IDs returned
by the backend through later edits.

In the manual form, open **Additional context** under a Persona or Scenario to
add optional metadata. Enter a unique key and a text value for each row. The
downloaded Specification preserves these values. Remove a row to omit it.
