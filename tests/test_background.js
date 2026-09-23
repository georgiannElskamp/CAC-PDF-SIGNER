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
function formAdapterTest() {
  const callbacks = {}, timers = [], clicks = [], errors = [], shown = [];
  const dialog = { show() { shown.push("native"); } };
  const originalShow = dialog.show;
  let modified = false, preview = true;
  const api = {
    asc_getPdfProps: vm.runInNewContext("(function(){return null})"),
    GetVersion: () => "9.4.0",
    isDocumentModified: () => modified,
    asc_getDocumentName: () => "form.pdf",
    pluginMethod_IsFillingFormMode: () => preview,
    pluginMethod_GetAllForms: () => [{ InternalId: "1603", FormKey: "Signature1", FormValue: "" }],
    asc_registerCallback: (name, fn) => { callbacks[name] = fn; },
    asc_unregisterCallback: (name, fn) => { if (callbacks[name] === fn) delete callbacks[name]; },
  };
  const host = {
    Asc: { editor: api },
    AscDesktopEditor: { LocalFileGetSourcePath: () => "C:\\Test User\\form.pdf" },
    Common: { Views: { PdfSignDialog: function () {} } },
  };
  host.Common.Views.PdfSignDialog.prototype = dialog;
  const context = { window: { setTimeout: (fn) => timers.push(fn) } };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root, "plugin/desktop-adapter.js"), "utf8"), context);
  const adapter = context.window.CACDesktop(host);
  adapter.attach((field) => clicks.push(field), (error) => errors.push(error));
  assert.equal(adapter.snapshot("Signature1").kind, "onlyoffice-form");
  const action = { type: 12, pr: {
    get_InternalId: () => "1603",
    get_FormPr: () => ({ get_Key: () => "Signature1" }),
  } };
  dialog.show();
  callbacks.asc_onShowContentControlsActions(action);
  timers.shift()();
  assert.deepEqual(clicks, ["Signature1"]);
  assert.deepEqual(shown, []);
  dialog.show();
  callbacks.asc_onShowContentControlsActions({ type: 4 });
  timers.shift()();
  assert.deepEqual(shown, ["native"]);
  preview = false;
  dialog.show();
  callbacks.asc_onShowContentControlsActions(action);
  timers.shift()();
  assert.deepEqual(shown, ["native", "native"]);
  modified = true;
  assert.throws(() => adapter.snapshot("Signature1"), /reopen/);
  callbacks.asc_onDocumentModifiedChanged();
  modified = false;
  assert.throws(() => adapter.snapshot("Signature1"), /reopen/);
  assert.equal(errors.length, 0);
  adapter.detach();
  assert.equal(dialog.show, originalShow);
  assert.equal(callbacks.asc_onShowContentControlsActions, undefined);
}
formAdapterTest();
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
    CACDesktop: () => ({ attach: () => events.push("attach"), detach: () => events.push("detach") }),
  };
  vm.runInNewContext(fs.readFileSync(path.join(root, "plugin/standalone-background.js"), "utf8"), context);
  const started = context.Asc.plugin.init();
  await context.Asc.plugin.init();
  assert.deepEqual(events, ["preflight"]);
  if (unload) handlers.unload();
  if (fail) reject(new Error("Startup failed")); else resolve({ ok: true });
  await started;
  assert.deepEqual(events, unload ? ["preflight", "detach", "close"] : ["preflight", fail ? "error" : "attach"]);
}
Promise.all([
  startupTest(false, false), startupTest(true, false), startupTest(false, true),
  startupTest(false, false, { editorType: "word", documentTitle: "form.pdf" }),
])
  .then(() => console.log("PASS: PDF and ONLYOFFICE form clicks, unsaved edits, version guard, startup and cleanup"))
  .catch(error => { console.error(error); process.exitCode = 1; });
