/* Editor-side client for the native signing host. */
window.CACNativeClient = function () {
  "use strict";
  const frame = document.createElement("iframe");
  frame.hidden = true;
  frame.src =
    "onlyoffice://plugin/" + new URL("native.html", location.href).href;
  let active = null;
  let ready = false;
  let closed = false;
  let loadError = null;
  const readyWaiters = [];
  const readyTimer = setTimeout(() => {
    loadError = new Error(
      "The bundled CAC component could not load. Reinstall the plugin.",
    );
    while (readyWaiters.length) readyWaiters.shift().reject(loadError);
  }, 15000);
  function receive(event) {
    if (
      event.source !== frame.contentWindow ||
      event.origin !== "onlyoffice://plugin"
    )
      return;
    const data = event.data;
    if (!data || data.channel !== "cac-native-v1") return;
    if (data.type === "ready") {
      ready = true;
      loadError = null;
      clearTimeout(readyTimer);
      while (readyWaiters.length) readyWaiters.shift().resolve();
    } else if (
      data.type === "result" &&
      data.result &&
      active &&
      data.id === active.id
    ) {
      const pending = active;
      active = null;
      data.result.ok
        ? pending.resolve(data.result)
        : pending.reject(
            new Error(data.result.error || "CAC signing did not finish."),
          );
    }
  }
  window.addEventListener("message", receive);
  document.body.appendChild(frame);
  async function call(request) {
    if (closed) throw new Error("The CAC plugin was disabled.");
    if (active) throw new Error("Finish the current signing operation first.");
    if (loadError) throw loadError;
    if (!ready)
      await new Promise((resolve, reject) =>
        readyWaiters.push({ resolve, reject }),
      );
    if (closed) throw new Error("The CAC plugin was disabled.");
    if (active) throw new Error("Finish the current signing operation first.");
    const id = crypto.randomUUID
      ? crypto.randomUUID()
      : Array.from(crypto.getRandomValues(new Uint32Array(4))).join("-");
    return new Promise((resolve, reject) => {
      active = { id, resolve, reject };
      try {
        frame.contentWindow.postMessage(
          { channel: "cac-native-v1", type: "run", id, request },
          "onlyoffice://plugin",
        );
      } catch (error) {
        active = null;
        reject(error);
      }
    });
  }
  function close() {
    closed = true;
    clearTimeout(readyTimer);
    window.removeEventListener("message", receive);
    if (active) active.reject(new Error("The CAC plugin was disabled."));
    active = null;
    while (readyWaiters.length)
      readyWaiters.shift().reject(new Error("The CAC plugin was disabled."));
    frame.remove();
  }
  return { call, close };
};
