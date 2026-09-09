# metis-web

This is the standalone browser client for the wizard. It talks to `apps/api` through the versioned
REST routes only. It does not import Python packages, read Python files, or depend on API storage.

The browser owns local Interview records and the display transcript in IndexedDB. The JSON
`InterviewState` is sent back to the API unchanged; browser IDs, timestamps, and transcript entries
never enter that state.

Render requests by their discriminator and supplied fields. Do not derive stages, apply patches, or
recreate wizard validation rules in TypeScript. Regenerate `src/generated/api.ts` from FastAPI's
runtime OpenAPI document with `npm run generate:api`; `npm run check:api` fails when the committed
module is stale.

Useful commands:

```bash
npm install
npm run dev          # use a separate `PORT=8001 uv run metis-api` process
npm run format:check
npm run typecheck
npm test
npm run build
npm run generate:api # update the committed OpenAPI types
npm run check:api
```
