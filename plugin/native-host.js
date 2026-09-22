(() => {
  "use strict";
  const channel = "cac-native-v1";
  let active = null;
  function send(data) {
    parent.postMessage({ channel, ...data }, "*");
  }
  function executable() {
    let own = location.href.replace(/^onlyoffice:\/\/plugin\//, "");
    if (own.startsWith("/")) own = "file://" + own;
    const url = new URL("native/cac-signer.exe", own);
    if (url.protocol !== "file:" || url.hostname)
      throw new Error(
        "Install this plugin locally through ONLYOFFICE Plugin Manager.",
      );
    if (!/^\/[A-Za-z]:\//.test(url.pathname)) {
      if (!/Linux/.test(navigator.platform || ""))
        throw new Error("This package supports Windows and Linux desktop editors.");
      const launcher = decodeURIComponent(new URL("launch-linux.sh", own).pathname);
      if (!launcher.startsWith("/") || /[\r\n\0]/.test(launcher))
        throw new Error("Unsupported plugin installation path.");
      return '/bin/sh "' + launcher.replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"';
    }
    const path = decodeURIComponent(url.pathname)
      .replace(/^\/([A-Za-z]:)/, "$1")
      .replace(/\//g, "\\");
    if (!/^[A-Za-z]:\\/.test(path) || /[\r\n"]/g.test(path))
      throw new Error("Unsupported plugin installation path.");
    if (/\s/.test(path)) {
      throw new Error(
        "This ONLYOFFICE Windows build cannot launch plugins from paths containing spaces. A Windows profile path without spaces is required.",
      );
    }
    return path;
  }
  function run(id, request) {
    if (active) {
      send({
        type: "result",
        id,
        result: { ok: false, error: "Another CAC operation is in progress." },
      });
      return;
    }
    let process;
    let startup;
    let responded = false;
    let inputSent = false;
    function finish(result) {
      if (responded) return;
      responded = true;
      clearTimeout(startup);
      send({ type: "result", id, result });
    }
    try {
      if (!request || !["sign", "health"].includes(request.op))
        throw new Error("Unknown CAC operation.");
      const input = JSON.stringify(request) + "\n";
      if (input.length > 56 * 1024 * 1024)
        throw new Error("The PDF is too large.");
      if (typeof ExternalProcess !== "function")
        throw new Error(
          "This ONLYOFFICE build does not support the bundled CAC component.",
        );
      process = new ExternalProcess(executable(), {});
      active = process;
      startup = setTimeout(() => {
        finish({
          ok: false,
          error:
            "The bundled signing component did not start. Reinstall the plugin.",
        });
        process.end();
        active = null;
      }, 30000);
      process.onprocess = (type, message) => {
        if (type === 2) {
          finish({
            ok: false,
            error:
              "The signing component stopped before completion. Any signed recovery copy is retained; click the field to retry.",
          });
          if (active === process) active = null;
          setTimeout(() => process.end(), 0);
          return;
        }
        if (type !== 0 || responded) return;
        let response;
        try {
          response = JSON.parse(message);
        } catch (_) {
          return;
        }
        if (response.event === "ready" && !inputSent) {
          if (response.version !== CAC_BUNDLE.version) {
            finish({
              ok: false,
              error:
                "The bundled signing component version does not match the plugin.",
            });
            process.end();
            active = null;
            return;
          }
          clearTimeout(startup);
          inputSent = true;
          let position = 0;
          function writeChunk() {
            if (active !== process || responded) return;
            try {
              const end = Math.min(position + 65536, input.length);
              process.stdin(input.slice(position, end));
              position = end;
              // Microtasks avoid timer throttling in hidden editor frames.
              if (position < input.length) queueMicrotask(writeChunk);
            } catch (error) {
              finish({
                ok: false,
                error:
                  "The signing request could not be delivered. " +
                  (error.message || String(error)),
              });
              process.end();
              if (active === process) active = null;
            }
          }
          writeChunk();
        } else if (response.event === "result") {
          finish(response);
        }
      };
      process.start();
      if (process.id < 0)
        throw new Error(
          "ONLYOFFICE could not start the bundled CAC component.",
        );
    } catch (error) {
      finish({ ok: false, error: error.message || String(error) });
      if (process && process.id >= 0) process.end();
      active = null;
    }
  }
  window.addEventListener("message", (event) => {
    // Desktop Chromium reports local file parents as file://; other builds use null.
    if (event.source !== parent || !["null", "file://"].includes(event.origin))
      return;
    const data = event.data;
    if (
      !data ||
      data.channel !== channel ||
      data.type !== "run" ||
      typeof data.id !== "string" ||
      data.id.length > 100
    )
      return;
    run(data.id, data.request);
  });
  window.addEventListener("unload", () => {
    if (active) active.end();
    active = null;
  });
  send({ type: "ready" });
})();
