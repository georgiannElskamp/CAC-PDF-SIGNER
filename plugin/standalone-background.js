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
      const source = adapter.snapshot(field);
      const request = {
        op: "sign",
        field,
        name: source.name,
        sourcePath: source.sourcePath,
      };
      if (source.kind === "onlyoffice-form") request.kind = source.kind;
      else request.pdf = base64(source.bytes);
      const result = await client.call(request);
      if (result.cancelled) return;
      if (!result.saved || !result.integrityVerified)
        throw new Error("The signed copy could not be verified and saved.");
      completed.add(field);
      try {
        if (typeof result.path !== "string" || !/\.pdf$/i.test(result.path))
          throw new Error("The saved PDF path was not returned.");
        // Open by path; the recent-file command expects an index.
        const desktop = parent.AscDesktopEditor;
        if (typeof desktop._openExternalReference !== "function")
          throw new Error(
            "This editor does not expose the native file opener.",
          );
        desktop._openExternalReference(result.path);
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
  Asc.plugin.init = async function () {
    const info = Asc.plugin.info || {};
    if (info.editorType && info.editorType !== "pdf" && info.editorSubType !== "pdf") return;
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
