import type { CompileResult } from "./transport/api";

const DOWNLOAD_NAMES = ["profile.yaml", "experiment.yaml"] as const;

export function downloadCompileResult(
  result: CompileResult,
  ownerDocument: Pick<Document, "createElement"> = document,
  urlApi: Pick<typeof URL, "createObjectURL" | "revokeObjectURL"> = URL,
): void {
  for (const name of DOWNLOAD_NAMES) {
    const url = urlApi.createObjectURL(
      new Blob([result[name]], { type: "text/yaml" }),
    );
    const anchor = ownerDocument.createElement("a");
    anchor.href = url;
    anchor.download = name;
    anchor.click();
    anchor.remove();
    urlApi.revokeObjectURL(url);
  }
}
