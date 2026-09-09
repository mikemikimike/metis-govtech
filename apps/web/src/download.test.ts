import assert from "node:assert/strict";
import test from "node:test";
import { downloadCompileResult } from "./download.ts";

test("offers exactly the two compiled YAML documents with stable names", () => {
  const downloads: string[] = [];
  const revoked: string[] = [];
  const document = {
    createElement: () => ({
      href: "",
      download: "",
      click() {
        downloads.push(this.download);
      },
      remove() {},
    }),
  } as unknown as Document;
  const urlApi = {
    createObjectURL: () => "blob:metis",
    revokeObjectURL: (url: string) => revoked.push(url),
  } as Pick<typeof URL, "createObjectURL" | "revokeObjectURL">;

  downloadCompileResult(
    { "profile.yaml": "profile", "experiment.yaml": "experiment" },
    document,
    urlApi,
  );

  assert.deepEqual(downloads, ["profile.yaml", "experiment.yaml"]);
  assert.deepEqual(revoked, ["blob:metis", "blob:metis"]);
});
