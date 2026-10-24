import assert from "node:assert/strict";
import { test } from "node:test";
import {
  bindingFromDraft,
  emptyConnectionDraft,
  errorsByField,
  startConnection,
  type ConnectionDraft,
} from "./connection.ts";
import type { ConnectionCheckResult } from "./transport/api.ts";

const http: ConnectionDraft = {
  ...emptyConnectionDraft(),
  mode: "run",
  name: " Policy assistant ",
  specUrl: "${APP_URL}/openapi.json",
  secretEnv: "APP_KEY",
  secretHeaders: "POST /chat X-Api-Key APP_HEADER",
  forbiddenCalls: "DELETE /**",
  tlsVerify: false,
  startUrl: "https://ignored.example",
};

const valid = (draft: ConnectionDraft): ConnectionCheckResult => ({
  binding: bindingFromDraft(draft) as ConnectionCheckResult["binding"],
  errors: [],
  live: false,
  probes: [],
  status: "unchecked",
});

test("an HTTP draft becomes binding fields with no browser field", () => {
  assert.deepEqual(bindingFromDraft(http), {
    schema_version: 1,
    identity: { name: "Policy assistant" },
    transport: "http",
    spec_url: "${APP_URL}/openapi.json",
    auth: { secret_env: "APP_KEY" },
    secret_headers: [
      { match: "POST /chat", header: "X-Api-Key", env: "APP_HEADER" },
    ],
    forbidden_calls: ["DELETE /**"],
    tls_verify: false,
  });
});

test("a browser draft sends the sign-in note and its variable names only", () => {
  const binding = bindingFromDraft({
    ...http,
    transport: "browser",
    startUrl: "${APP_URL}/login",
    loginNote: "Type {{secret:APP_USER}}.",
    loginSecrets: "APP_USER, APP_PASSWORD",
  });
  assert.deepEqual(binding, {
    schema_version: 1,
    identity: { name: "Policy assistant" },
    transport: "browser",
    start_url: "${APP_URL}/login",
    login: {
      note: "Type {{secret:APP_USER}}.",
      secrets: ["APP_USER", "APP_PASSWORD"],
    },
  });
});

test("field errors from the API mark the matching draft field", () => {
  const errors = errorsByField({
    binding: null,
    errors: [
      { loc: ["auth", "secret_env"], msg: "String should match pattern" },
      {
        loc: ["identity", "name"],
        msg: "String should have at least 1 character",
      },
      { loc: [], msg: "Value error, a http binding needs spec_url" },
    ],
    live: false,
    status: "unchecked",
  });
  assert.equal(errors.secretEnv, "String should match pattern");
  assert.equal(errors.name, "Required");
  assert.equal(errors.binding, "Value error, a http binding needs spec_url");
});

test("the Interview starts with a connection only in run mode with a valid binding", () => {
  assert.equal(startConnection({ ...http, mode: "spec" }, valid(http)), null);
  assert.equal(startConnection(http, valid(http))?.transport, "http");
  assert.equal(
    startConnection(http, {
      binding: null,
      errors: [{ loc: ["identity", "name"], msg: "too short" }],
      live: false,
      status: "unchecked",
    }),
    null,
  );
});

test("sign-in variables with no sign-in steps still reach the check", () => {
  const binding = bindingFromDraft({
    ...http,
    transport: "browser",
    startUrl: "${APP_URL}/login",
    loginSecrets: "APP_USER",
  });
  assert.deepEqual(binding.login, { note: "", secrets: ["APP_USER"] });
});
