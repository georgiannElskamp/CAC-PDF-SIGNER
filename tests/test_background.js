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
async function startupTest(fail, unload) {
  const events = [], handlers = {};
  let resolve, reject;
  const pending = new Promise((ok, no) => { resolve = ok; reject = no; });
  const context = {
    Asc: { plugin: { info: { editorType: "pdf" } } },
    window: { addEventListener: (name, fn) => { handlers[name] = fn; } },
    parent: { Common: { UI: { warning: () => events.push("error") } } },
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
Promise.all([startupTest(false, false), startupTest(true, false), startupTest(false, true)])
  .then(() => console.log("PASS: fields, unsaved edits, version guard, startup preflight and cleanup"))
  .catch(error => { console.error(error); process.exitCode = 1; });
