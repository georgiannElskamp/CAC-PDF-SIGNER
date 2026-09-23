const fs = require("fs");
const vm = require("vm");
const assert = require("assert/strict");
const path = require("path");
const root = path.resolve(__dirname, "..");
function adapterTest() {
  let timer,
    onModified,
    formReads = 0,
    clicks = [],
    errors = [];
  const empty = {
    type: 33,
    u0: () => 11,
    Cte: () => false,
    Vh: function () {},
  };
  const signed = {
    type: 33,
    u0: () => 12,
    Cte: () => true,
    Vh: function () {},
  };
  const original = empty.Vh;
  const widgets = [empty, signed];
  const fields = [
    { type: 33, AP: { i: 11 }, name: "PreparedBy", Sig: 0 },
    { type: 33, AP: { i: 12 }, name: "ReviewedBy", Sig: 1 },
  ];
  const api = {
    // Exact editor fingerprint.
    asc_getPdfProps: vm.runInNewContext(
      "(function(){return this.jf?this.jf.vWe():null})",
    ),
    isDocumentModified: () => false,
    asc_getDocumentName: () => "test.pdf",
    asc_getFilePath: () => "C:\\test.pdf",
    asc_registerCallback: (e, fn) => {
      onModified = fn;
    },
    asc_unregisterCallback() {},
    jf: {
      Qd: () => ({ lC: widgets }),
      file: {
        Mp: {
          getInteractiveFormsInfo: () => {
            formReads++;
            return { Fields: fields };
          },
          getFileBinary: () => Buffer.from("%PDF-1.7 test"),
        },
      },
    },
  };
  const host = {
    Asc: { editor: api },
    AscDesktopEditor: {
      SaveFilenameDialog() {},
      LocalFileGetSourcePath: () => "C:\\test.pdf",
    },
  };
  const context = {
    window: {
      setInterval: (f) => {
        timer = f;
        return 1;
      },
      AscDesktopEditor: host.AscDesktopEditor,
    },
    clearInterval() {},
    Uint8Array,
    console,
  };
  vm.createContext(context);
  vm.runInContext(
    fs.readFileSync(path.join(root, "plugin/desktop-adapter.js"), "utf8"),
    context,
  );
  const adapter = context.window.CACDesktop(host);
  adapter.attach(
    (f) => clicks.push(f),
    (e) => errors.push(e),
  );
  timer();
  empty.Vh();
  signed.Vh();
  assert.deepEqual(clicks, ["PreparedBy"]);
  assert.equal(errors.length, 0);
  assert.equal(
    Buffer.from(adapter.snapshot("PreparedBy").bytes).toString(),
    "%PDF-1.7 test",
  );
  api.isDocumentModified = () => true;
  assert.throws(() => adapter.snapshot("PreparedBy"), /Save your PDF edits/);
  api.isDocumentModified = () => false;
  assert.throws(() => adapter.snapshot("ReviewedBy"), /already signed/);
  widgets.splice(1, 1);
  const readsBeforeIdle = formReads;
  timer();
  timer();
  assert.equal(formReads, readsBeforeIdle);
  const later = { type: 33, u0: () => 13, Cte: () => false, Vh: function () {} };
  widgets.push(later);
  fields.push({ type: 33, AP: { i: 13 }, name: "ApprovedBy", Sig: 0 });
  timer();
  later.Vh();
  assert.deepEqual(clicks, ["PreparedBy", "ApprovedBy"]);
  api.isDocumentModified = () => true;
  onModified();
  api.isDocumentModified = () => false;
  assert.throws(() => adapter.snapshot("PreparedBy"), /reopen the PDF/);
  adapter.detach();
  assert.equal(empty.Vh, original);
  api.asc_getPdfProps = () => null;
  assert.throws(() => context.window.CACDesktop(host), /adapter update/);
  api.GetVersion = () => "99.0.0";
  assert.throws(() => context.window.CACDesktop(host), /ONLYOFFICE 99\.0\.0 needs/);
  api.GetVersion = () => { throw new Error("Unavailable"); };
  assert.throws(() => context.window.CACDesktop(host), /ONLYOFFICE unknown needs/);
}
adapterTest();
async function formAdapterTest(version) {
  const callbacks = {}, timers = [], clicks = [], errors = [], shown = [];
  const reads = [];
  const dialog = { show() { shown.push("native"); } };
  const originalShow = dialog.show;
  let modified = false, preview = true, sourcePath = "C:\\Test User é%\\form.pdf";
  let documentName = "form.pdf";
  const api = {
    asc_getPdfProps: vm.runInNewContext("(function(){return null})"),
    GetVersion: () => version,
    isDocumentModified: () => modified,
    asc_getDocumentName: () => documentName,
    pluginMethod_IsFillingFormMode: () => preview,
    pluginMethod_GetAllForms: () => [{ InternalId: "1603", FormKey: "Signature1", FormValue: "" }],
    asc_registerCallback: (name, fn) => { callbacks[name] = fn; },
    asc_unregisterCallback: (name, fn) => { if (callbacks[name] === fn) delete callbacks[name]; },
  };
  const host = {
    Asc: { editor: api },
    AscCommon: { Ss: { tia: "file:///C:/Test%20User%20%C3%A9%25/recover/DE_123" } },
    AscDesktopEditor: {
      LocalFileGetSourcePath: () => sourcePath,
      loadLocalFile(path, callback) {
        reads.push(path);
        callback(Buffer.from(path.endsWith("asc_name.info")
          ? `<info type="87" name="${documentName}" />` : "%PDF-1.7 recovery"));
      },
    },
    Common: { Views: { PdfSignDialog: function () {} } },
  };
  host.Common.Views.PdfSignDialog.prototype = dialog;
  class DOMParser {
    parseFromString(xml) {
      const match = xml.match(/<info type="([^"]+)" name="([^"]+)"\s*\/>/);
      return {
        documentElement: {
          tagName: match ? "info" : "error",
          getAttribute: (name) => match ? match[name === "type" ? 1 : 2] : null,
        },
        getElementsByTagName: () => match ? [] : ["parsererror"],
      };
    }
  }
  const context = {
    window: { setTimeout: (fn) => timers.push(fn) },
    setTimeout, clearTimeout, DOMParser, TextDecoder, URL, Uint8Array,
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root, "plugin/desktop-adapter.js"), "utf8"), context);
  const adapter = context.window.CACDesktop(host);
  adapter.attach((field) => clicks.push(field), (error) => errors.push(error));
  const snapshot = await adapter.snapshot("Signature1");
  assert.equal(snapshot.kind, "onlyoffice-form");
  assert.equal(Buffer.from(snapshot.bytes).toString(), "%PDF-1.7 recovery");
  assert.equal(snapshot.sourcePath, sourcePath);
  assert.ok(adapter.stillCurrent(snapshot, "Signature1"));
  assert.deepEqual(reads, [
    "C:\\Test User é%\\recover\\DE_123\\asc_name.info",
    "C:\\Test User é%\\recover\\DE_123\\form.pdf",
  ]);
  for (const name of ["form#1?.pdf", "..%2Foutside.pdf", "..%5Coutside.pdf"]) {
    documentName = name;
    sourcePath = `C:\\Test User é%\\${name}`;
    const next = await adapter.snapshot("Signature1");
    assert.equal(next.name, name);
    assert.equal(reads.at(-1), `C:\\Test User é%\\recover\\DE_123\\${name}`);
  }
  documentName = "form.pdf";
  sourcePath = snapshot.sourcePath;
  const action = { type: 12, pr: {
    get_InternalId: () => "1603",
    get_FormPr: () => ({ get_Key: () => "Signature1" }),
  } };
  dialog.show();
  callbacks.asc_onShowContentControlsActions(action);
  timers.shift()();
  assert.deepEqual(clicks, ["Signature1"]);
  assert.deepEqual(shown, []);
  api.pluginMethod_GetAllForms = () => { throw new Error("form inspection failed"); };
  dialog.show();
  callbacks.asc_onShowContentControlsActions(action);
  timers.shift()();
  assert.deepEqual(shown, []);
  assert.match(errors.pop().message, /form inspection failed/);
  api.pluginMethod_GetAllForms = () => [{ InternalId: "1603", FormKey: "Signature1", FormValue: "" }];
  dialog.show();
  callbacks.asc_onShowContentControlsActions({ type: 12, pr: {} });
  timers.shift()();
  assert.deepEqual(shown, []);
  assert.match(errors.pop().message, /could not be identified/);
  api.pluginMethod_IsFillingFormMode = () => { throw new Error("mode inspection failed"); };
  dialog.show();
  callbacks.asc_onShowContentControlsActions(action);
  timers.shift()();
  assert.deepEqual(shown, []);
  assert.match(errors.pop().message, /mode inspection failed/);
  api.pluginMethod_IsFillingFormMode = () => preview;
  dialog.show();
  callbacks.asc_onShowContentControlsActions({ type: 4 });
  timers.shift()();
  assert.deepEqual(shown, ["native"]);
  preview = false;
  dialog.show();
  callbacks.asc_onShowContentControlsActions(action);
  timers.shift()();
  assert.deepEqual(shown, ["native", "native"]);
  assert.equal(adapter.stillCurrent(snapshot, "Signature1"), false);
  preview = true;
  const originalLoad = host.AscDesktopEditor.loadLocalFile;
  host.AscDesktopEditor.loadLocalFile = (path, callback) => {
    originalLoad(path, callback);
    if (path.endsWith("asc_name.info")) sourcePath = "C:\\Test User é%\\another.pdf";
  };
  await assert.rejects(adapter.snapshot("Signature1"), /active PDF form changed/);
  sourcePath = snapshot.sourcePath;
  host.AscDesktopEditor.loadLocalFile = (path, callback) => {
    if (path.endsWith("asc_name.info")) callback(null);
    else originalLoad(path, callback);
  };
  await assert.rejects(adapter.snapshot("Signature1"), /recovery copy is missing/);
  host.AscDesktopEditor.loadLocalFile = originalLoad;
  modified = true;
  await assert.rejects(adapter.snapshot("Signature1"), /reopen/);
  callbacks.asc_onDocumentModifiedChanged();
  modified = false;
  await assert.rejects(adapter.snapshot("Signature1"), /reopen/);
  assert.equal(adapter.stillCurrent(snapshot, "Signature1"), false);
  assert.equal(errors.length, 0);
  adapter.detach();
  assert.equal(dialog.show, originalShow);
  assert.equal(callbacks.asc_onShowContentControlsActions, undefined);
  api.GetVersion = () => "9.4.0.128";
  assert.throws(() => context.window.CACDesktop(host), /adapter update/);
}
async function startupTest(fail, unload, info = { editorType: "pdf" }) {
  const events = [], handlers = {};
  let resolve, reject;
  const pending = new Promise((ok, no) => { resolve = ok; reject = no; });
  const context = {
    Asc: { plugin: { info } },
    window: { addEventListener: (name, fn) => { handlers[name] = fn; } },
    parent: {
      Asc: { editor: { pluginMethod_GetAllForms() {} } },
      Common: { UI: { warning: () => events.push("error") } },
    },
    CACNativeClient: () => ({ call: (request) => {
      assert.equal(request.op, "preflight");
      events.push("preflight"); return pending;
    }, close: () => events.push("close") }),
    CACDesktop: () => ({
      attach: () => events.push("attach"), detach: () => events.push("detach"),
    }),
  };
  vm.runInNewContext(fs.readFileSync(path.join(root, "plugin/standalone-background.js"), "utf8"), context);
  const started = context.Asc.plugin.init();
  await context.Asc.plugin.init();
  assert.deepEqual(events, ["preflight"]);
  if (unload) handlers.unload();
  if (fail) reject(new Error("Startup failed"));
  else resolve({ ok: true });
  await started;
  assert.deepEqual(events, unload ? ["preflight", "detach", "close"] : ["preflight", fail ? "error" : "attach"]);
}
async function formHandoffTest() {
  let click, current = true;
  const requests = [], warnings = [], opened = [];
  const context = {
    Asc: { plugin: { info: { editorType: "word", documentTitle: "form.pdf" } } },
    window: { addEventListener() {} },
    btoa: (value) => Buffer.from(value, "binary").toString("base64"),
    parent: {
      Asc: { editor: { pluginMethod_GetAllForms() {} } },
      AscDesktopEditor: { _openExternalReference: (path) => opened.push(path) },
      Common: { UI: { warning: (message) => warnings.push(message) } },
    },
    CACDesktop: () => ({
      snapshot: () => ({ kind: "onlyoffice-form", bytes: Buffer.from("%PDF-review"),
        sourcePath: "C:\\Test User\\form.pdf", name: "form.pdf" }),
      stillCurrent: () => current,
      attach: (handler) => { click = handler; }, detach() {},
    }),
    CACNativeClient: () => ({
      call: async (request) => {
        requests.push(request);
        return request.op === "preflight" ? { ok: true } : {
          ok: true, prepared: true, field: request.field + "_af_image",
          sha256: "b".repeat(64), path: "C:\\review.pdf",
        };
      },
      close() {},
    }),
  };
  vm.runInNewContext(fs.readFileSync(path.join(root, "plugin/standalone-background.js"), "utf8"), context);
  await context.Asc.plugin.init();
  click("Signature1");
  await new Promise(setImmediate);
  assert.equal(requests[1].op, "prepare");
  assert.equal(Buffer.from(requests[1].pdf, "base64").toString(), "%PDF-review");
  assert.equal(requests[1].sourcePath, "C:\\Test User\\form.pdf");
  assert.deepEqual(opened, ["C:\\review.pdf"]);
  click("Signature1");
  await new Promise(setImmediate);
  assert.equal(requests.length, 2);
  current = false;
  click("Signature2");
  await new Promise(setImmediate);
  assert.equal(requests.length, 3);
  assert.equal(warnings.length, 1);
  assert.deepEqual(opened, ["C:\\review.pdf"]);
}
Promise.all([
  formAdapterTest("9.4.0"), formAdapterTest("9.4.0.129"),
  startupTest(false, false), startupTest(true, false), startupTest(false, true),
  startupTest(false, false, { editorType: "word", documentTitle: "form.pdf" }),
  formHandoffTest(),
])
  .then(() => console.log("PASS: PDF and ONLYOFFICE form clicks, unsaved edits, version guard, startup and cleanup"))
  .catch(error => { console.error(error); process.exitCode = 1; });
