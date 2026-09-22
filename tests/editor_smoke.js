/* Run only against a disposable ONLYOFFICE profile and the generated fixture. */
const fs = require("node:fs");
const assert = require("node:assert/strict");
const GUID = "asc.{9A58C737-A6B4-4E31-8D3F-2C940B716EF9}";
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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

async function until(probe, message, timeout = 90000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await probe();
    if (value) return value;
    await delay(500);
  }
  throw new Error(message);
}

async function smoke(port, packagePath, version) {
  const page = await until(async () => {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(2000) });
      return (await response.json()).find((p) => p.url.includes("doctype=pdf"));
    } catch (_) { return null; }
  }, "The PDF editor did not open.");
  const socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let sequence = 0;
  const pending = new Map(), contexts = new Set();
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.method === "Runtime.executionContextCreated") contexts.add(message.params.context.id);
    if (message.method === "Runtime.executionContextDestroyed") contexts.delete(message.params.executionContextId);
    const request = pending.get(message.id);
    if (request) {
      pending.delete(message.id);
      clearTimeout(request.timer);
      message.error ? request.reject(new Error(message.error.message)) : request.resolve(message.result);
    }
  };
  function call(method, params) {
    const id = ++sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method} timed out`)); }, 125000);
      pending.set(id, { resolve, reject, timer });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async function evaluate(contextId, expression) {
    const reply = await call("Runtime.evaluate", { contextId, expression, awaitPromise: true, returnByValue: true, timeout: 120000 });
    if (reply.exceptionDetails) throw new Error(reply.exceptionDetails.exception?.description || reply.exceptionDetails.text);
    return reply.result.value;
  }
  let context, installed = false;
  let stage = "editor startup";
  const progress = (value) => { stage = value; console.log(`Checking: ${stage}`); };
  const run = (fn, ...args) => evaluate(context, `(${fn.toString()})(${args.map((a) => JSON.stringify(a)).join(",")})`);
  try {
    await call("Runtime.enable");
    context = await until(async () => {
      for (const id of contexts) {
        try {
          if (await evaluate(id, "typeof PDFE !== 'undefined' && typeof Asc !== 'undefined' && !!Asc.editor?.jf?.file?.Mp")) return id;
        } catch (error) {
          if (!/context.*(find|destroy)|find.*context/i.test(error.message)) throw error;
        }
      }
      return null;
    }, "The tested PDF editor interface is unavailable.");
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
    if (installed && context) await run((guid) => {
      Asc.editor.asc_pluginStop(guid);
      AscDesktopEditor.PluginUninstall(guid, false);
    }, GUID).catch(() => {});
    socket.close();
    for (const request of pending.values()) clearTimeout(request.timer);
  }
}

const args = process.argv.slice(2);
if (args[0] === "--fixture" && args.length === 2) fixture(args[1]);
else if (args.length === 4 && args[0] === "--disposable-profile" && /^\d+$/.test(args[1])) {
  smoke(Number(args[1]), args[2], args[3]).catch((error) => { console.error(error.message); process.exitCode = 1; });
} else {
  console.error("Usage: node tests/editor_smoke.js --fixture <pdf>\n       node tests/editor_smoke.js --disposable-profile <debug-port> <native-package-path> <version>");
  process.exitCode = 2;
}
