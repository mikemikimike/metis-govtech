import type { FixtureMetadata } from "./api";

export const ACCEPTED_FIXTURE_EXTENSIONS = [
  "csv",
  "pdf",
  "docx",
  "xlsx",
  "pptx",
  "txt",
  "json",
  "png",
  "jpg",
  "gif",
  "webp",
  "md",
  "html",
] as const;

export const FIXTURE_MAX_FILES = 20;
export const FIXTURE_MAX_BYTES = 100_000_000;

export interface FixtureFileLike {
  name: string;
  size: number;
}

export function normalizeFixtureName(raw: string): string {
  const name = raw.normalize("NFC").trim();
  if (
    !name ||
    name === "." ||
    name === ".." ||
    /[\\/\0\u0000-\u001f<>:\"|?*]/.test(name) ||
    /[. ]$/.test(name)
  ) {
    throw new Error("File names must be portable basenames.");
  }
  const stem = (name.split(".", 1)[0] ?? "").toUpperCase();
  if (/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/.test(stem)) {
    throw new Error("File names cannot use a reserved device name.");
  }
  return name;
}

function extension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot + 1).toLowerCase();
}

function identity(name: string): string {
  return name.normalize("NFC").toLocaleLowerCase();
}

export function validateFixtureSelection(
  files: readonly FixtureFileLike[],
  library: readonly FixtureMetadata[],
): string[] {
  const existing = new Set(library.map((item) => identity(item.name)));
  const incoming = new Set<string>();
  const names: string[] = [];
  let total = library.reduce((sum, item) => sum + item.size, 0);
  for (const file of files) {
    const name = normalizeFixtureName(file.name);
    if (!(ACCEPTED_FIXTURE_EXTENSIONS as readonly string[]).includes(extension(name))) {
      throw new Error(
        `Unsupported file type. Accepted: ${ACCEPTED_FIXTURE_EXTENSIONS.join(", ")}.`,
      );
    }
    const key = identity(name);
    if (existing.has(key) || incoming.has(key)) {
      throw new Error(`A file named ${name} is already uploaded.`);
    }
    incoming.add(key);
    names.push(name);
    total += file.size;
  }
  if (library.length + files.length > FIXTURE_MAX_FILES) {
    throw new Error(`An experiment can contain at most ${FIXTURE_MAX_FILES} files.`);
  }
  if (total > FIXTURE_MAX_BYTES) {
    throw new Error("Fixture files can use at most 100 MB in total.");
  }
  return names;
}

export function fixtureNames(files: readonly FixtureFileLike[]): string[] {
  return files.map((file) => normalizeFixtureName(file.name));
}
