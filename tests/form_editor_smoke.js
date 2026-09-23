/* Run only with a disposable editor profile and the synthetic form fixture. */
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { fileURLToPath } = require("node:url");
const { connect, until } = require("./editor_cdp");

const GUID = "asc.{9A58C737-A6B4-4E31-8D3F-2C940B716EF9}";
const sha256 = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");

async function check(port, packagePath, sourcePath, replacementPath, statePath, version) {
  const sourceName = path.basename(sourcePath);
  const editor = await connect(port, (page) => {
    try { return new URL(page.url).searchParams.get("title") === sourceName; }
    catch (_) { return false; }
  }, "typeof Asc !== 'undefined' && !!Asc.editor && typeof Asc.editor.pluginMethod_GetAllForms === 'function' && typeof AscDesktopEditor !== 'undefined'");
  const { run, call } = editor;
  let installed = false, review;
  try {
    const form = await until(() => run(() => {
      const fields = Asc.editor.pluginMethod_GetAllForms();
      return fields?.length === 1 ? fields[0] : null;
    }), "The ONLYOFFICE form fixture did not load.");
    assert.equal(form.FormKey, "Signature1");
    assert.equal(form.FormValue, "");
    assert.equal(await run(() => Asc.editor.GetVersion()), "9.4.0");
    assert.equal(await run(() => Asc.editor.isDocumentModified()), false);
    assert.equal(await run(() => AscDesktopEditor.LocalFileGetSourcePath().replace(/\\/g, "/")), sourcePath.replace(/\\/g, "/"));
    assert.equal(await run((guid) => JSON.parse(AscDesktopEditor.GetInstallPlugins()).some((group) =>
      (group.pluginsData || []).some((plugin) => plugin.guid === guid)), GUID), false);

    installed = true;
    assert.equal(await run((file) => AscDesktopEditor.PluginInstall(file), packagePath), true);
    const listed = await until(() => run((guid) => {
      const plugin = DE.getController("Common.Controllers.Plugins").backgroundPlugins?.find(
        (entry) => entry.get("guid") === guid);
      if (!plugin) return null;
      const config = plugin.get("original");
      return { version: config.version, type: config.variations[0].type };
    }, GUID), "The form editor did not list the plugin under Background plugins.");
    assert.deepEqual(listed, { version, type: "background" });
    await run((guid) => {
      if (!Asc.editor.getUsedBackgroundPlugins().includes(guid)) Asc.editor.asc_pluginRun(guid, 0, "");
    }, GUID);
    try {
      await until(() => run(() => typeof Common !== "undefined" &&
        /claimed/.test(String(Common.Views?.PdfSignDialog?.prototype?.show))),
        "The background plugin did not attach to the form signature control.");
    } catch (error) {
      const state = await run((guid) => {
        const frame = document.getElementById("iframe_" + guid);
        let adapter = "unavailable";
        if (frame) {
          try {
            const probe = frame.contentWindow.CACDesktop(window);
            probe.detach();
            adapter = "ready";
          } catch (cause) { adapter = String(cause.message).slice(0, 160); }
        }
        return {
          frame: !!frame, adapter,
          dialog: typeof Common === "undefined" ? "unavailable" :
            typeof Common.Views?.PdfSignDialog?.prototype?.show,
          used: Asc.editor.getUsedBackgroundPlugins().includes(guid),
          plugin: frame?.contentWindow?.Asc?.plugin?.info?.editorType || "unavailable",
        };
      }, GUID);
      throw new Error(`${error.message} ${JSON.stringify(state)}`);
    }
    const health = await run(async (guid) => {
      const frame = document.getElementById("iframe_" + guid);
      const client = frame.contentWindow.CACNativeClient();
      try { return await client.call({ op: "preflight" }); } finally { client.close(); }
    }, GUID);
    assert.equal(health.ok, true);
    assert.equal(health.version, version);
    assert.equal(health.cardChecked, false);

    await run(() => {
      if (Asc.editor.pluginMethod_IsFillingFormMode()) return;
      const item = [...document.querySelectorAll("a")].find((a) =>
        a.textContent.includes("See how the form will look like when filling out"));
      if (!item) throw new Error("The form Preview control is missing.");
      item.click();
    });
    await until(() => run(() => Asc.editor.pluginMethod_IsFillingFormMode()), "The form did not enter Preview mode.");
    const recovery = await run(() => ({
      directory: AscCommon.Ss.tia,
      name: Asc.editor.asc_getDocumentName(),
    }));
    assert.equal(recovery.name, sourceName);
    const recoveryDirectory = new URL(recovery.directory);
    assert.equal(recoveryDirectory.protocol, "file:");
    const recoveryPath = fileURLToPath(new URL(sourceName, new URL(recovery.directory + "/")));
    const loadedHash = sha256(fs.readFileSync(recoveryPath));
    const loaded = await run(async () => {
      const directory = new URL(AscCommon.Ss.tia + "/");
      const file = new URL(Asc.editor.asc_getDocumentName(), directory);
      const nativePath = decodeURIComponent(file.pathname).replace(/^\/([A-Za-z]:)/, "$1").replace(/\//g,
        navigator.platform.startsWith("Win") ? "\\" : "/");
      return await new Promise((resolve) => AscDesktopEditor.loadLocalFile(nativePath, (bytes) =>
        resolve(bytes ? Array.from(new Uint8Array(bytes)).length : 0)));
    });
    assert.ok(loaded > 10000, "The form recovery snapshot was not readable.");

    const originalHash = sha256(fs.readFileSync(sourcePath));
    let sourceChanged = false;
    try {
      fs.copyFileSync(replacementPath, sourcePath);
      sourceChanged = true;
      assert.notEqual(sha256(fs.readFileSync(sourcePath)), originalHash);
    } catch (error) {
      if (process.platform !== "win32" || !["EBUSY", "EPERM", "EACCES"].includes(error.code)) throw error;
      assert.equal(sha256(fs.readFileSync(sourcePath)), originalHash);
    }
    const point = await run((id) => {
      const [left, top, right, bottom] = Asc.editor.asc_GetContentControlBoundingRect(id);
      const rect = document.getElementById("editor_sdk").getBoundingClientRect();
      return { x: rect.left + (left + right) / 2, y: rect.top + (top + bottom) / 2 };
    }, form.InternalId);
    for (const [type, extra] of [
      ["mouseMoved", {}], ["mousePressed", { button: "left", clickCount: 1 }],
      ["mouseReleased", { button: "left", clickCount: 1 }],
    ]) await call("Input.dispatchMouseEvent", { type, ...point, ...extra });

    const preparedDirectory = path.join(statePath, "Prepared");
    const prepared = await until(() => {
      if (!fs.existsSync(preparedDirectory)) return null;
      const names = fs.readdirSync(preparedDirectory).filter((name) => /^CAC-review-[0-9a-f]{32}\.pdf$/.test(name));
      return names.length === 1 ? path.join(preparedDirectory, names[0]) : null;
    }, "The form click did not produce an unsigned review PDF.");
    const metadata = JSON.parse(fs.readFileSync(prepared.replace(/\.pdf$/, ".json"), "utf8"));
    assert.equal(metadata.field, "Signature1_af_image");
    assert.equal(metadata.sha256, sha256(fs.readFileSync(prepared)));
    assert.equal(metadata.source.replace(/\\/g, "/"), sourcePath.replace(/\\/g, "/"));
    assert.equal(fs.readFileSync(prepared).includes(Buffer.from("/MetaOForm")), false);

    review = await connect(port, (page) => {
      try { return new URL(page.url).searchParams.get("title") === path.basename(prepared); }
      catch (_) { return false; }
    }, "typeof Asc !== 'undefined' && !!Asc.editor && !!Asc.editor.jf?.file?.Mp");
    const visible = await until(() => review.run(() =>
      Asc.editor.jf.file.Mp.getInteractiveFormsInfo()?.Fields?.filter((field) => field.type === 33)
        .map((field) => ({ name: field.name, signed: !!field.Sig }))),
    "The review PDF did not expose a standard signature field.");
    assert.deepEqual(visible, [{ name: "Signature1_af_image", signed: false }]);
    const openedPath = await review.run(() => AscDesktopEditor.LocalFileGetSourcePath());
    const openedFile = fs.statSync(openedPath, { bigint: true });
    const preparedFile = fs.statSync(prepared, { bigint: true });
    assert.equal(openedFile.dev, preparedFile.dev);
    assert.equal(openedFile.ino, preparedFile.ino);
    assert.equal(sha256(fs.readFileSync(openedPath)), metadata.sha256);
    assert.equal(await run(() => Asc.editor.pluginMethod_GetAllForms()[0].FormValue), "");
    assert.equal(sha256(fs.readFileSync(recoveryPath)), loadedHash);
    fs.mkdirSync(statePath, { recursive: true });
    const retainedRecovery = path.join(statePath, "editor-loaded-form.pdf");
    fs.copyFileSync(recoveryPath, retainedRecovery);
    console.log(JSON.stringify({ prepared, recoveryPath: retainedRecovery,
      comparisonPath: sourceChanged ? sourcePath : replacementPath, sourceChanged }));
    console.log(`PASS: real form click, card-free preparation, editor-loaded bytes, and visible unsigned review field; disk replacement ${sourceChanged ? "tested" : "blocked by Windows file lock"}.`);
  } finally {
    if (review) review.close();
    if (installed) await run((guid) => {
      Asc.editor.asc_pluginStop(guid);
      AscDesktopEditor.PluginUninstall(guid, false);
    }, GUID).catch(() => {});
    editor.close();
  }
}

const args = process.argv.slice(2);
if (args.length === 7 && args[0] === "--disposable-profile" && /^\d+$/.test(args[1])) {
  check(Number(args[1]), ...args.slice(2)).catch((error) => { console.error(error.stack); process.exitCode = 1; });
} else {
  console.error("Usage: node tests/form_editor_smoke.js --disposable-profile <port> <package> <source> <replacement> <state> <version>");
  process.exitCode = 2;
}
