(() => {
  "use strict";
  const VERSION = CAC_CONNECTION.version;
  let adapter,
    busy = false,
    lastError = "",
    completed = new Set();
  async function call(path, data) {
    const options = { headers: { "X-CAC-Token": CAC_CONNECTION.token } };
    if (data !== undefined) {
      options.method = "POST";
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(data);
    }
    let response;
    try {
      response = await fetch(CAC_CONNECTION.url + path, options);
    } catch (_) {
      throw new Error(
        "The CAC helper is not running. Open Start CAC Helper in your private installation folder, then click the signature box again.",
      );
    }
    const result = await response.json();
    if (!response.ok)
      throw new Error(result.error || "CAC signing could not finish.");
    return result;
  }
  function event(stage, error) {
    call("/event", {
      stage,
      version: VERSION,
      ...(error ? { error } : {}),
    }).catch(() => {});
  }
  function errorMessage(error) {
    const message = error.message || String(error);
    event("error", message);
    // An error is the only plugin UI. Successful signing has no plugin window.
    if (lastError !== message) {
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
      event("clicked");
      const source = adapter.snapshot(field);
      const health = await call("/health");
      if (health.version !== VERSION)
        throw new Error(
          "Restart Start CAC Helper to load the updated Save As support, then click the signature box again.",
        );
      const result = await call("/sign-auto", {
        pdf: base64(source.bytes),
        name: source.name,
        sourcePath: source.sourcePath,
        appearance: { field },
      });
      if (!result.integrityVerified)
        throw new Error("The PDF signature could not be verified.");
      event(result.recovered ? "signature_recovered" : "signed");
      event("save_dialog_requested");
      const save = await call("/save-dialog", { id: result.id });
      if (save.cancelled) {
        event("save_cancelled");
        return;
      }
      if (save.sha256 !== result.sha256)
        throw new Error(
          "The saved PDF did not match the verified signature. The recovery copy is retained.",
        );
      completed.add(field);
      event("saved");
      await call("/open", { id: result.id });
    } catch (error) {
      errorMessage(error);
    } finally {
      busy = false;
    }
  }
  Asc.plugin.init = function () {
    try {
      adapter = CACDesktop(parent);
      adapter.attach(sign, errorMessage);
      event("ready");
    } catch (error) {
      errorMessage(error);
    }
  };
  window.addEventListener("unload", () => adapter && adapter.detach());
})();
