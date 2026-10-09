const DOWNLOAD_NAME = "specification.zip";

export function downloadArchive(
  archive: Blob,
  ownerDocument: Pick<Document, "createElement"> = document,
  urlApi: Pick<typeof URL, "createObjectURL" | "revokeObjectURL"> = URL,
): void {
  const url = urlApi.createObjectURL(archive);
  const anchor = ownerDocument.createElement("a");
  anchor.href = url;
  anchor.download = DOWNLOAD_NAME;
  anchor.click();
  anchor.remove();
  urlApi.revokeObjectURL(url);
}
