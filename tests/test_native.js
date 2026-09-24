const fs = require("fs");
const vm = require("vm");
const assert = require("assert/strict");
const path = require("path");
const os = require("os");
const { spawnSync } = require("child_process");
const { pathToFileURL } = require("url");
function script(name) {
  return fs.readFileSync(path.join(__dirname, "../plugin", name), "utf8");
}
function harness(name, location, platform = "Win32") {
  const handlers = {},
    timers = new Map(),
    sent = [];
  let sequence = 0;
  const context = {
    URL,
    navigator: { platform },
    console,
    queueMicrotask: (fn) => {
      timers.set(++sequence, fn);
    },
    crypto: { randomUUID: () => "request-id" },
    location: { href: "file:///C:/Apps/plugin/standalone.html" },
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
    constructor(command, env) {
      this.command = command;
      this.env = env;
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
  if (location) context.location.href = location;
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
  assert.equal(process.env.CAC_SIGNER_EXE, "C:\\Apps\\plugin\\native\\cac-signer.exe");
  assert(process.command.startsWith("cmd.exe\t/q\t/d\t/v:off"));
  assert.equal(process.input, "");
  process.onprocess(0, JSON.stringify({ event: "ready", version: "0.5.0" }));
  while (h.timers.size) {
    for (const [id, timer] of [...h.timers]) {
      h.timers.delete(id);
      timer();
    }
  }
  assert.equal(process.input, JSON.stringify({ ...request, acknowledgeResult: true }) + "\n");
  process.onprocess(
    0,
    JSON.stringify({ event: "result", ok: true, saved: true }),
  );
  assert(process.input.endsWith('{"op":"ack"}\n'));
  assert.equal(h.sent.filter((x) => x.type === "result").length, 0,
    "Do not release the client while its completed worker is still exiting.");
  process.onprocess(2, "");
  for (const timer of h.timers.values()) timer();
  assert(!process.ended, "The editor already cleans up an exited worker.");
  assert.equal(h.sent.filter((x) => x.type === "result").length, 1);
  assert.equal(h.sent.at(-1).result.saved, true);
  h.handlers.unload();
  assert(!process.ended, "Closing a completed client must not race native cleanup.");
  h.handlers.message({
    ...event,
    data: { ...event.data, request: { op: "execute", command: "bad" } },
  });
  assert.match(h.sent.at(-1).result.error, /Unknown/);
  const prepare = harness("native-host.js");
  prepare.handlers.message({ ...event, source: prepare.context.parent,
    data: { ...event.data, request: { op: "prepare", pdf: "JVBERi0=", field: "Signature1" } } });
  assert(prepare.context.process, "A card-free prepare request must reach the bundled worker.");
  const crash = harness("native-host.js");
  crash.handlers.message({
    ...event,
    origin: "null",
    source: crash.context.parent,
  });
  crash.context.process.onprocess(2, "");
  assert.match(crash.sent.at(-1).result.error, /stopped before completion/);
  assert(!crash.context.process.ended);
  const cancelled = harness("native-host.js");
  cancelled.handlers.message({ ...event, source: cancelled.context.parent });
  cancelled.handlers.unload();
  assert(cancelled.context.process.ended, "Disabling the plugin still stops a running operation.");
  for (const [location, platform, expected] of [
    ["onlyoffice://plugin/file:///tmp/Test%20Folder/plugin/native.html", "Linux x86_64",
      '/bin/sh "/tmp/Test Folder/plugin/launch-linux.sh"'],
    ["onlyoffice://plugin//tmp/Test%20Folder/plugin/native.html", "Linux aarch64",
      '/bin/sh "/tmp/Test Folder/plugin/launch-linux.sh"'],
    ["onlyoffice://plugin/file:///tmp/test%24%28echo%20bad%29/plugin/native.html", "Linux x86_64",
      '/bin/sh "/tmp/test$(echo bad)/plugin/launch-linux.sh"'],
  ]) {
    const platformHost = harness("native-host.js", location, platform);
    platformHost.handlers.message({ ...event, source: platformHost.context.parent });
    assert.equal(platformHost.context.process.command, expected);
  }
  for (const name of ["Example User", "Test & User (QA)", "User 100% ! ^ name", "Test O'Brien é", "User %PATH% name"]) {
    const spacedWindows = launchHost("onlyoffice://plugin/file:///C:/" + encodeURIComponent(name) + "/plugin/native.html");
    assert(spacedWindows.command.includes('for\t%I\tin\t("%CAC_SIGNER_EXE%")\tdo\t"%~sI"'));
    assert(!spacedWindows.command.includes(" "));
    assert.equal(spacedWindows.env.CAC_SIGNER_EXE, "C:\\" + name + "\\plugin\\native\\cac-signer.exe");
  }
  const networkPath = launchHost("onlyoffice://plugin/file://server/share/plugin/native.html");
  assert.equal(networkPath.env.CAC_SIGNER_EXE, "\\\\server\\share\\plugin\\native\\cac-signer.exe");
  for (const [message, expected] of [["Permission denied at private path", /execution policy/],
                                    ["libpython failed to load Python", /required signing-runtime file/],
                                    ["filename or extension is too long", /path is too long/]]) {
    const failed = harness("native-host.js");
    failed.handlers.message({ ...event, source: failed.context.parent });
    failed.context.process.onprocess(1, message);
    failed.context.process.onprocess(2, "");
    assert.match(failed.sent.at(-1).result.error, expected);
    assert(!failed.sent.at(-1).result.error.includes("private path"));
  }
  for (const invalid of ["%00", "%0A", "%0D", "%22"]) {
    const blocked = harness("native-host.js", "onlyoffice://plugin/file:///C:/Test" + invalid + "/native.html");
    blocked.handlers.message({ ...event, source: blocked.context.parent });
    assert.equal(blocked.context.process, undefined);
    assert.match(blocked.sent.at(-1).result.error, /Unsupported/);
  }
}
function launchHost(location, platform = "Win32") {
  const h = harness("native-host.js", location, platform);
  h.handlers.message({
    source: h.context.parent,
    origin: "file://",
    data: { channel: "cac-native-v1", type: "run", id: "launch", request: { op: "health" } },
  });
  return h.context.process;
}
function launchPathTest() {
  if (!["win32", "linux"].includes(process.platform)) return;
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cac-launch-test-"));
  try {
    const names = ["Example User", "Test & User (QA)", "User 100% ! ^ name", "Test O'Brien é", "User %PATH% name"];
    if (process.platform === "linux") names.push('User $(echo bad) `echo bad` " \\ name');
    for (const name of names) {
      const directory = path.join(root, name, "plugin");
      const location = "onlyoffice://plugin/" + pathToFileURL(path.join(directory, "native.html")).href;
      let result;
      if (process.platform === "win32") {
        const worker = path.join(directory, "native/cac-signer.exe");
        fs.mkdirSync(path.dirname(worker), { recursive: true });
        // A real child verifies quoting and stdin/stdout without accessing a card.
        fs.copyFileSync(process.execPath, worker);
        const launch = launchHost(location);
        const split = launch.command.search(/\s/);
        result = spawnSync(launch.command.slice(0, split), [launch.command.slice(split + 1)], {
          windowsVerbatimArguments: true,
          windowsHide: true,
          env: { ...process.env, ...launch.env },
          input: 'process.stdout.write(JSON.stringify(process.execPath))',
          encoding: "utf8",
          timeout: 15000,
        });
        assert.equal(result.status, 0, result.stderr || String(result.error));
        assert.equal(fs.statSync(JSON.parse(result.stdout)).ino, fs.statSync(worker).ino);
      } else {
        const architecture = process.arch === "arm64" ? "linux-aarch64" : "linux-x86_64";
        const worker = path.join(directory, "native", architecture, "cac-signer");
        fs.mkdirSync(path.dirname(worker), { recursive: true });
        fs.writeFileSync(worker, '#!/bin/sh\nprintf "%s\\n" "$0"\ncat\n', { mode: 0o600 });
        const launcher = path.join(directory, "launch-linux.sh");
        fs.copyFileSync(path.join(__dirname, "../plugin/launch-linux.sh"), launcher);
        const launch = launchHost(location, "Linux x86_64");
        assert.equal(launch.command, '/bin/sh "' + launcher.replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"');
        result = spawnSync("/bin/sh", [launcher], {
          input: "request remains unchanged\n",
          encoding: "utf8",
          timeout: 15000,
        });
        assert.equal(result.status, 0, result.stderr || String(result.error));
        assert.equal(result.stdout, worker + "\nrequest remains unchanged\n");
      }
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
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
    Asc: { plugin: { info: { editorType: "word", editorSubType: "pdf" } } },
    btoa: (value) => Buffer.from(value, "binary").toString("base64"),
    CACNativeClient: () => ({
      call: (request) => {
        if (request.op === "preflight") return Promise.resolve({ ok: true });
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
  await context.Asc.plugin.init();
  const first = click("PreparedBy");
  await click("PreparedBy");
  assert.equal(requests.length, 1);
  finish({ cancelled: true });
  await first;
  assert.equal(opened.length, 0);
  const retry = click("PreparedBy");
  await Promise.resolve();
  assert.equal(requests.length, 2);
  assert.equal(requests[1].op, "sign");
  assert.ok(requests[1].pdf);
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
module.exports = { launchHost };
if (require.main === module) (async () => {
  await clientTest();
  hostTest();
  launchPathTest();
  await backgroundTest();
  console.log(
    "PASS: native origin checks, lifecycle, recovery errors, request chunking, startup timeout and spaced launch paths",
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
