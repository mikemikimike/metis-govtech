import assert from "node:assert/strict";
import test from "node:test";
import { downloadArchive } from "./download.ts";

test("offers one portable specification ZIP with a stable name", () => {
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

  downloadArchive(
    new Blob(["zip bytes"], { type: "application/zip" }),
    document,
    urlApi,
  );

  assert.deepEqual(downloads, ["specification.zip"]);
  assert.deepEqual(revoked, ["blob:metis"]);
});
