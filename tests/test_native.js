const fs = require("fs");
const vm = require("vm");
const assert = require("assert/strict");
const path = require("path");
function script(name) {
  return fs.readFileSync(path.join(__dirname, "../plugin", name), "utf8");
}
function harness(name) {
  const handlers = {},
    timers = new Map(),
    sent = [];
  let sequence = 0;
  const context = {
    URL,
    console,
    queueMicrotask: (fn) => {
      timers.set(++sequence, fn);
    },
    crypto: { randomUUID: () => "request-id" },
    location: { href: "file:///C:/Apps/plugin/background.html" },
    setTimeout(fn) {
      timers.set(++sequence, fn);
      return sequence;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
    window: {
      addEventListener: (name, fn) => (handlers[name] = fn),
      removeEventListener: (name) => delete handlers[name],
    },
    CAC_BUNDLE: { version: "0.5.0" },
    parent: { postMessage: (data) => sent.push(data) },
  };
  const frame = {
    contentWindow: { postMessage: (data) => sent.push(data) },
    remove() {
      this.removed = true;
    },
  };
  context.document = { createElement: () => frame, body: { appendChild() {} } };
  context.ExternalProcess = class {
    constructor(command) {
      this.command = command;
      this.id = -1;
      this.input = "";
      context.process = this;
    }
    start() {
      this.id = 1;
    }
    stdin(input) {
      this.input += input;
    }
    end() {
      this.ended = true;
    }
  };
  if (name === "native-host.js")
    context.location.href =
      "onlyoffice://plugin/file:///C:/Apps/plugin/native.html";
  vm.runInNewContext(script(name), context);
  return { context, handlers, timers, sent, frame };
}
async function clientTest() {
  const h = harness("native-client.js"),
    client = h.context.window.CACNativeClient();
  const send = (data) =>
    h.handlers.message({
      source: h.frame.contentWindow,
      origin: "onlyoffice://plugin",
      data: { channel: "cac-native-v1", ...data },
    });
  const promise = client.call({ op: "health" });
  send({ type: "ready" });
  await Promise.resolve();
  assert.equal(h.sent.length, 1);
  h.handlers.message({
    source: {},
    origin: "onlyoffice://plugin",
    data: {
      channel: "cac-native-v1",
      type: "result",
      id: "request-id",
      result: { ok: true },
    },
  });
  await assert.rejects(client.call({ op: "health" }), /current signing/);
  send({
    type: "result",
    id: "request-id",
    result: { ok: true, version: "0.5.0" },
  });
  assert.equal((await promise).version, "0.5.0");
  const pending = client.call({ op: "health" });
  client.close();
  await assert.rejects(pending, /disabled/);
  assert(h.frame.removed);
  const failed = harness("native-client.js"),
    timedOut = failed.context.window.CACNativeClient();
  [...failed.timers.values()][0]();
  await assert.rejects(timedOut.call({ op: "health" }), /could not load/);
  timedOut.close();
}
function hostTest() {
  const h = harness("native-host.js");
  const request = {
    op: "sign",
    pdf: "A".repeat(4 * 1024 * 1024),
    field: "Example",
  };
  const event = {
    source: h.context.parent,
    origin: "file://",
    data: { channel: "cac-native-v1", type: "run", id: "1", request },
  };
  h.handlers.message({ ...event, source: {} });
  assert.equal(h.context.process, undefined);
  h.handlers.message({ ...event, origin: "https://example.com" });
  assert.equal(h.context.process, undefined);
  h.handlers.message(event);
  const process = h.context.process;
  assert.equal(process.command, "C:\\Apps\\plugin\\native\\cac-signer.exe");
  assert.equal(process.input, "");
  process.onprocess(0, JSON.stringify({ event: "ready", version: "0.5.0" }));
  while (h.timers.size) {
    for (const [id, timer] of [...h.timers]) {
      h.timers.delete(id);
      timer();
    }
  }
  assert.equal(process.input, JSON.stringify(request) + "\n");
  process.onprocess(
    0,
    JSON.stringify({ event: "result", ok: true, saved: true }),
  );
  process.onprocess(2, "");
  for (const timer of h.timers.values()) timer();
  assert(process.ended);
  assert.equal(h.sent.filter((x) => x.type === "result").length, 1);
  h.handlers.message({
    ...event,
    data: { ...event.data, request: { op: "execute", command: "bad" } },
  });
  assert.match(h.sent.at(-1).result.error, /Unknown/);
  const crash = harness("native-host.js");
  crash.handlers.message({
    ...event,
    origin: "null",
    source: crash.context.parent,
  });
  crash.context.process.onprocess(2, "");
  assert.match(crash.sent.at(-1).result.error, /stopped before completion/);
}
async function backgroundTest() {
  let click, finish;
  const requests = [],
    opened = [],
    errors = [],
    handlers = {};
  const context = {
    window: { addEventListener: (name, fn) => (handlers[name] = fn) },
    parent: {
      Common: { UI: { warning: (value) => errors.push(value) } },
      AscDesktopEditor: { _openExternalReference: (path) => opened.push(path) },
    },
    Asc: { plugin: {} },
    btoa: (value) => Buffer.from(value, "binary").toString("base64"),
    CACNativeClient: () => ({
      call: (request) => {
        requests.push(request);
        return new Promise((resolve) => (finish = resolve));
      },
      close() {},
    }),
    CACDesktop: () => ({
      attach: (fn) => (click = fn),
      detach() {},
      snapshot: () => ({
        bytes: Buffer.from("%PDF-test"),
        name: "example.pdf",
        sourcePath: "C:\\example.pdf",
      }),
    }),
  };
  vm.runInNewContext(script("standalone-background.js"), context);
  context.Asc.plugin.init();
  const first = click("PreparedBy");
  await click("PreparedBy");
  assert.equal(requests.length, 1);
  finish({ cancelled: true });
  await first;
  assert.equal(opened.length, 0);
  const retry = click("PreparedBy");
  assert.equal(requests.length, 2);
  assert.equal(requests[1].op, "sign");
  finish({
    saved: true,
    integrityVerified: true,
    path: "C:\\example-signed.pdf",
  });
  await retry;
  await click("PreparedBy");
  assert.equal(requests.length, 2);
  assert.equal(errors.length, 0);
  assert.deepEqual(opened, ["C:\\example-signed.pdf"]);
  handlers.unload();
}
(async () => {
  await clientTest();
  hostTest();
  await backgroundTest();
  console.log(
    "PASS: native origin checks, lifecycle, recovery errors, request chunking and startup timeout",
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
