(() => {
  "use strict";
  const channel = "cac-native-v1";
  let active = null;
  function send(data) {
    parent.postMessage({ channel, ...data }, "*");
  }
  function workerLaunch() {
    let own = location.href.replace(/^onlyoffice:\/\/plugin\//, "");
    if (own.startsWith("/")) own = "file://" + own;
    const url = new URL("native/cac-signer.exe", own);
    if (url.protocol !== "file:")
      throw new Error(
        "Install this plugin locally through ONLYOFFICE Plugin Manager.",
      );
    if (!/^\/[A-Za-z]:\//.test(url.pathname) && !url.hostname) {
      if (!/Linux/.test(navigator.platform || ""))
        throw new Error("This package supports Windows and Linux desktop editors.");
      const launcher = decodeURIComponent(new URL("launch-linux.sh", own).pathname);
      if (!launcher.startsWith("/") || /[\r\n\0]/.test(launcher))
        throw new Error("Unsupported plugin installation path.");
      return {
        command: '/bin/sh "' + launcher.replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"',
        env: {},
      };
    }
    const path = (url.hostname ? "\\\\" + url.hostname : "") + decodeURIComponent(url.pathname)
      .replace(/^\/([A-Za-z]:)/, "$1")
      .replace(/\//g, "\\");
    if (!/^(?:[A-Za-z]:\\|\\\\[^\\]+\\)/.test(path) || /[\r\n\0"]/.test(path))
      throw new Error("Unsupported plugin installation path.");
    // Tabs bypass the editor's first-space lookup. Short names, when available,
    // also avoid native loaders' long-path limits without changing OS settings.
    return {
      command: 'cmd.exe\t/q\t/d\t/v:off\t/s\t/c\t"for\t%T\tin\t("%TEMP%")\tdo\tset\t"TEMP=%~sT"&for\t%T\tin\t("%TMP%")\tdo\tset\t"TMP=%~sT"&for\t%I\tin\t("%CAC_SIGNER_EXE%")\tdo\t"%~sI""',
      env: { CAC_SIGNER_EXE: path },
    };
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
    let completedResult = null;
    let inputSent = false;
    let startupError = "";
    function classifyStartupError(message) {
      if (/filename or extension is too long|path too long/i.test(message))
        return "The Windows runtime path is too long. Install the plugin in a shorter local profile path.";
      if (/permission denied|operation not permitted|failed to map segment|access is denied/i.test(message))
        return "The operating system blocked the signing runtime. Check plugin file permissions and application execution policy.";
      if (/GLIBC_|GLIBCXX_|version .* not found|Exec format error|not a valid Win32 application|not compatible with the version of Windows/i.test(message))
        return "The bundled runtime is not compatible with this system's libraries or CPU architecture.";
      if (/failed to load Python|libpython|shared libraries|cannot find|not found/i.test(message))
        return "A required signing-runtime file could not load. Check that Plugin Manager extracted the complete package and that security software has not blocked it.";
      return "";
    }
    function finish(result) {
      if (responded) return;
      responded = true;
      clearTimeout(startup);
      send({ type: "result", id, result });
    }
    try {
      if (!request || !["sign", "health", "preflight"].includes(request.op))
        throw new Error("Unknown CAC operation.");
      const input = JSON.stringify({ ...request, acknowledgeResult: true }) + "\n";
      if (input.length > 56 * 1024 * 1024)
        throw new Error("The PDF is too large.");
      if (typeof ExternalProcess !== "function")
        throw new Error(
          "This ONLYOFFICE build does not support the bundled CAC component.",
        );
      const launch = workerLaunch();
      process = new ExternalProcess(launch.command, launch.env);
      active = process;
      startup = setTimeout(() => {
        finish({
          ok: false,
          error:
            startupError || "The signing runtime did not start within 60 seconds. Check application execution policy and the plugin installation.",
        });
        process.end();
        active = null;
      }, 60000);
      process.onprocess = (type, message) => {
        if (type === 1 && !inputSent) {
          startupError = classifyStartupError(String(message).slice(0, 4096)) || startupError;
          return;
        }
        if (type === 2) {
          if (active === process) active = null;
          finish(completedResult || {
            ok: false,
            error:
              startupError || "The signing component stopped before completion. Any signed recovery copy is retained; click the field to retry.",
          });
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
        } else if (response.event === "result" && !completedResult) {
          completedResult = response;
          try { process.stdin('{"op":"ack"}\n'); } catch (_) { /* Worker timeout also releases it. */ }
          // The editor cleans up exited workers. Deliver after its exit callback
          // so closing the client cannot race native process cleanup.
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
