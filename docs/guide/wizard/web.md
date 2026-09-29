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

2. Set `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `INTERVIEW_MODEL`. The API does not start when one
   of them is missing. `INTERVIEW_MODEL` has no default here, which is different from the CLI.
   `JUDGE_MODEL` and `USER_AGENT_MODEL` are Engine settings. The API does not use them.
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

1. Enter a description of the target system.
2. Select who the evaluation is for. Hover over or focus a Perspective to see its guiding question.
3. Select all ARC capabilities that you know the system has. The list can be empty.
4. Select Low, Medium, or High confidence. The value states how complete the full selection is.
5. Select **Start interview**. This sends all opening values in one request.

The web client gets the opening text, Perspectives, capability catalogue, and document limits from
the API. It keeps the returned Interview state and sends the whole state with each answer. The API
does not save the state.

## Add documents

1. Select the plus button in the opening message.
2. If a file name does not make the purpose of a document clear, explain it in the same message.
3. Check the reading status of each file. Remove an unreadable file, or keep it without extracted
   text.

Document facts:

- The browser shows the accepted file types and size limits.
- The API extracts text from UTF-8 TXT, Markdown, PDF text layers, and DOCX files.
- The API does not run OCR. Scanned PDFs give no text.
- The Wizard can suggest an opening document as a Scenario fixture. Review each suggestion under
  **Files sent to your system**.
- The final package contains only files that a Scenario uses.

## Finish and download

1. Answer each Interview screen.
2. Review the final Personas and Scenarios.
3. Select **Continue** on the final review screen to complete the Interview.
4. Select **Download specification** to download `experiment.zip`.

To finish early, select **Skip interview and download specification**. The Wizard checks whether
the specification is ready. It can ask for more information or a document review before it
completes the Interview.

The archive contains:

```text
experiment.zip
├── experiment.yaml
├── profile.yaml
└── fixtures/
```

The browser sends only the original fixture files that the current Scenarios use. The API builds
the archive for that request and does not keep the files.

## Write the Experiment directly

Use **Write it yourself** when you already know the Experiment to run. This path does not use the
Interview and creates no Interview record.

1. Select **Write it yourself**.
2. Set the Experiment ID and description.
3. Add Personas and Scenarios from each section header. Set trial counts, Persona references,
   fixture files, and scorers.
4. Select **Done** to close an item editor. Select **Edit** to open it again.
5. Select **Download experiment.zip**.

Editor rules:

- A new Scenario selects all named Personas.
- A new Persona is added to all existing Scenarios.

The archive contains a runnable `experiment.yaml`, the selected fixtures, and a small supporting
`profile.yaml` for report generation.

## Browser storage and current limits

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
