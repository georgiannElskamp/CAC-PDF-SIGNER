/* Run only against a disposable ONLYOFFICE profile and the generated fixture. */
const fs = require("node:fs");
const assert = require("node:assert/strict");
const { connect, until } = require("./editor_cdp");
const GUID = "asc.{9A58C737-A6B4-4E31-8D3F-2C940B716EF9}";

function fixture(destination) {
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [5 0 R] /SigFlags 3 >> >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << >> /Contents 4 0 R /Annots [5 0 R] >>",
    "<< /Length 0 >>\nstream\n\nendstream",
    "<< /Type /Annot /Subtype /Widget /FT /Sig /T (InstallationTest) /Rect [54 365 424 463] /F 4 /P 3 0 R >>",
  ];
  let pdf = "%PDF-1.7\n", offsets = [0];
  objects.forEach((object, i) => {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${i + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${offsets.length}\n0000000000 65535 f \n`;
  pdf += offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("");
  pdf += `trailer\n<< /Size ${offsets.length} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  fs.writeFileSync(destination, pdf);
}

async function smoke(port, packagePath, version, fixtureName) {
  const editor = await connect(port, (p) => p.url.includes("doctype=pdf") &&
    (!fixtureName || new URL(p.url).searchParams.get("title") === fixtureName),
    "typeof PDFE !== 'undefined' && typeof Asc !== 'undefined' && !!Asc.editor && typeof AscDesktopEditor !== 'undefined'");
  const { run } = editor;
  let installed = false;
  let stage = "editor startup";
  const progress = (value) => { stage = value; console.log(`Checking: ${stage}`); };
  try {
    progress("adapter interface discovery");
    await until(() => run(() => !!Asc.editor?.jf?.file?.Mp && typeof Asc.editor.jf.Qd === "function"),
      "Unsupported PDF interface: inspect both the plugin adapter and test harness before diagnosing compatibility.");
    assert.equal(await run((guid) => JSON.parse(AscDesktopEditor.GetInstallPlugins()).some((g) => (g.pluginsData || []).some((p) => p.guid === guid)), GUID), false,
      "CAC is already installed. Use a disposable profile.");
    const initial = await until(() => run(() => {
      const fields = Asc.editor.jf.file.Mp.getInteractiveFormsInfo()?.Fields;
      return fields?.length ? fields.map((f) => ({ name: f.name, type: f.type, signed: !!f.Sig })) : null;
    }), "The installation fixture's signature field did not load.");
    assert.deepEqual(initial, [{ name: "InstallationTest", type: 33, signed: false }], "Open only the generated installation fixture.");
    for (let cycle = 0; cycle < 2; cycle++) {
      progress(`install cycle ${cycle + 1}`);
      installed = true;
      assert.equal(await run((file) => AscDesktopEditor.PluginInstall(file), packagePath), true, "Native plugin installation failed.");
      const listed = await until(() => run((guid) => {
        const controller = PDFE.getController("Common.Controllers.Plugins");
        const plugin = controller.backgroundPlugins?.find((p) => p.get("guid") === guid);
        if (!plugin) return null;
        const config = plugin.get("original");
        return { version: config.version, type: config.variations[0].type };
      }, GUID), "The plugin was not listed under Background plugins.");
      assert.deepEqual(listed, { version, type: "background" });
      progress("background startup");
      await run((guid) => {
        if (!Asc.editor.getUsedBackgroundPlugins().includes(guid)) Asc.editor.asc_pluginRun(guid, 0, "");
      }, GUID);
      await until(() => run(() => {
        const fields = Asc.editor.jf.Qd().lC.filter((w) => w.type === 33);
        return fields.length === 1 && fields.every((w) => String(w.Vh).includes("onClick(f.name)"));
      }), "The background plugin did not finish preflight and attach its field handler.");
      progress("native preflight");
      const result = await run(async (guid) => {
        const frame = document.getElementById("iframe_" + guid);
        const client = frame.contentWindow.CACNativeClient();
        try { return await client.call({ op: "preflight" }); } finally { client.close(); }
      }, GUID);
      assert.equal(result.ok, true);
      assert.equal(result.version, version);
      assert.equal(result.desktopReady, true);
      assert.equal(result.recoveryWritable, true);
      assert.equal(result.cardChecked, false);
      progress("disable");
      await run((guid) => Asc.editor.asc_pluginStop(guid), GUID);
      await until(() => run((guid) => !document.getElementById("iframe_" + guid) &&
        Asc.editor.jf.Qd().lC.every((w) => /^function\(\)\{\}$/.test(String(w.Vh).replace(/\s/g, ""))), GUID),
      "Disabling the plugin did not restore the field handler.");
      progress("uninstall");
      await run((guid) => AscDesktopEditor.PluginUninstall(guid, false), GUID);
      await until(() => run((guid) => !JSON.parse(AscDesktopEditor.GetInstallPlugins()).some((g) => (g.pluginsData || []).some((p) => p.guid === guid)) &&
        !PDFE.getController("Common.Controllers.Plugins").backgroundPlugins.some((p) => p.get("guid") === guid) &&
        !Asc.editor.getUsedBackgroundPlugins().includes(guid) &&
        !document.getElementById("iframe_" + guid) && Asc.editor.jf.Qd().lC.every((w) => /^function\(\)\{\}$/.test(String(w.Vh).replace(/\s/g, ""))), GUID),
      "Uninstall did not remove the plugin and restore the field handler.");
      installed = false;
    }
    console.log(`PASS: ONLYOFFICE installation, background listing, native preflight, uninstall and reinstall (${version}). No card accessed.`);
  } catch (error) {
    throw new Error(`${stage}: ${error.message}`, { cause: error });
  } finally {
    if (installed) await run((guid) => {
      Asc.editor.asc_pluginStop(guid);
      AscDesktopEditor.PluginUninstall(guid, false);
    }, GUID).catch(() => {});
    editor.close();
  }
}

const args = process.argv.slice(2);
if (args[0] === "--fixture" && args.length === 2) fixture(args[1]);
else if ((args.length === 4 || args.length === 5) && args[0] === "--disposable-profile" && /^\d+$/.test(args[1])) {
  smoke(Number(args[1]), args[2], args[3], args[4]).catch((error) => { console.error(error.message); process.exitCode = 1; });
} else {
  console.error("Usage: node tests/editor_smoke.js --fixture <pdf>\n       node tests/editor_smoke.js --disposable-profile <debug-port> <native-package-path> <version> [fixture-name]");
  process.exitCode = 2;
}
