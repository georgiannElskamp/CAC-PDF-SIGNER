(() => {
  "use strict";
  let adapter,
    client,
    initialized = false,
    disposed = false,
    busy = false,
    lastError = "";
  const completed = new Set();
  function errorMessage(error) {
    const message = error.message || String(error);
    if (lastError === message) return;
    lastError = message;
    const safe = message.replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
    parent.Common.UI.warning({ title: "CAC signature", msg: safe });
  }
  function base64(bytes) {
    const parts = [];
    for (let i = 0; i < bytes.length; i += 32768)
      parts.push(String.fromCharCode(...bytes.subarray(i, i + 32768)));
    return btoa(parts.join(""));
  }
  async function sign(field) {
    if (busy || completed.has(field)) return;
    busy = true;
    lastError = "";
    try {
      const source = await adapter.snapshot(field);
      if (source.kind === "onlyoffice-form") {
        const result = await client.call({
          op: "prepare",
          field,
          name: source.name,
          sourcePath: source.sourcePath,
          pdf: base64(source.bytes),
        });
        if (!result.prepared || !/^[0-9a-f]{64}$/.test(result.sha256 || "") ||
            result.field !== field + "_af_image" || !adapter.stillCurrent(source, field))
          throw new Error("The PDF form changed during preparation. Reopen it before signing.");
        openPdf(result.path);
        completed.add(field);
        return;
      }
      const request = {
        op: "sign",
        field,
        name: source.name,
        sourcePath: source.sourcePath,
        pdf: base64(source.bytes),
      };
      const result = await client.call(request);
      if (result.cancelled) return;
      if (!result.saved || !result.integrityVerified)
        throw new Error("The signed copy could not be verified and saved.");
      completed.add(field);
      try {
        openPdf(result.path);
      } catch (_) {
        errorMessage(
          new Error("The signed PDF was saved. Open it from: " + result.path),
        );
      }
    } catch (error) {
      errorMessage(error);
    } finally {
      busy = false;
    }
  }
  function openPdf(path) {
    if (typeof path !== "string" || !/\.pdf$/i.test(path))
      throw new Error("The PDF path was not returned.");
    const desktop = parent.AscDesktopEditor;
    if (typeof desktop?._openExternalReference !== "function")
      throw new Error("This editor does not expose the native file opener.");
    desktop._openExternalReference(path);
  }
  Asc.plugin.init = async function () {
    const info = Asc.plugin.info || {};
    const formPdf = info.editorType === "word" &&
      /\.pdf$/i.test(info.documentTitle || "") &&
      typeof parent.Asc?.editor?.pluginMethod_GetAllForms === "function";
    if (info.editorType && info.editorType !== "pdf" && info.editorSubType !== "pdf" && !formPdf) return;
    if (initialized || disposed) return;
    initialized = true;
    try {
      adapter = CACDesktop(parent);
      client = CACNativeClient();
      await client.call({ op: "preflight" });
      if (disposed) return;
      adapter.attach(sign, errorMessage);
    } catch (error) {
      if (!disposed) errorMessage(error);
    }
  };
  window.addEventListener("unload", () => {
    disposed = true;
    if (adapter) adapter.detach();
    if (client) client.close();
  });
})();
