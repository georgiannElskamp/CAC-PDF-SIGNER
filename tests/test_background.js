const fs = require("fs");
const vm = require("vm");
const assert = require("assert/strict");
const path = require("path");
const root = path.resolve(__dirname, "..");
function adapterTest() {
  let timer,
    onModified,
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
  const fields = [
    { type: 33, AP: { i: 11 }, name: "PreparedBy", Sig: 0 },
    { type: 33, AP: { i: 12 }, name: "ReviewedBy", Sig: 1 },
  ];
  const api = {
    // Preserve the exact observed editor function; formatting must not alter this fixture.
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
      Qd: () => ({ lC: [empty, signed] }),
      file: {
        Mp: {
          getInteractiveFormsInfo: () => ({ Fields: fields }),
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
  api.isDocumentModified = () => true;
  onModified();
  api.isDocumentModified = () => false;
  assert.throws(() => adapter.snapshot("PreparedBy"), /reopen the PDF/);
  adapter.detach();
  assert.equal(empty.Vh, original);
  api.asc_getPdfProps = () => null;
  assert.throws(() => context.window.CACDesktop(host), /adapter update/);
}
adapterTest();
console.log("PASS: field targeting, filled-field rejection, unsaved-edit guard, version guard and cleanup");
