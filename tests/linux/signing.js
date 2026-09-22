const fs = require("node:fs");
const assert = require("node:assert/strict");
const cp = require("node:child_process");
const crypto = require("node:crypto");
const GUID = "asc.{9A58C737-A6B4-4E31-8D3F-2C940B716EF9}";
const home = process.env.HOME;
const source = home + "/Documents/installation-test.pdf";
const output = home + "/Documents/signed validation.pdf";
const recovery = home + "/.local/share/ONLYOFFICE-CAC-Signature/Signed";
const root = "/input";
const evidence = "/evidence";
const delay = ms => new Promise(r => setTimeout(r, ms));
const digest = path => crypto.createHash("sha256").update(fs.readFileSync(path)).digest("hex");
const native = (...args) => cp.execFileSync("xdotool", args, {env:{...process.env,DISPLAY:process.env.DISPLAY},encoding:"utf8"});
function windows(title) {
  try { return native("search","--onlyvisible","--name","^"+title+"$").trim().split("\n").filter(Boolean); }
  catch (e) { if (e.status===1) return []; throw e; }
}
async function until(probe, message, timeout=90000) {
  const deadline=Date.now()+timeout;
  while (Date.now()<deadline) { const result=await probe(); if(result) return result; await delay(250); }
  throw new Error(message);
}
function key(id,...keys) { native("windowfocus","--sync",String(id)); native("key","--clearmodifiers",...keys); }
function type(id,value) { native("windowfocus","--sync",String(id)); native("type","--clearmodifiers","--delay","20",value); }
async function dialog(title) { return until(()=>windows(title)[0],title+" dialog missing"); }
async function main() {
  const report={version:JSON.parse(fs.readFileSync(root + "/metadata.json", "utf8")).plugin.tag,os:"Debian 12 x86_64 / glibc 2.36",uid:1000,sourceHash:digest(source),simulatedToken:true};
  assert(!fs.existsSync(output),"Output already exists");
  const page = await until(async()=>{
    try { return (await (await fetch("http://127.0.0.1:9251/json/list")).json()).find(p=>p.url.includes("doctype=pdf")); }
    catch (_) { return null; }
  },"PDF editor did not open");
  const socket=new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  let sequence=0;
  const pending=new Map(), contexts=new Set();
  socket.onmessage=({data})=>{
    const message=JSON.parse(data);
    if(message.method==="Runtime.executionContextCreated") contexts.add(message.params.context.id);
    if(message.method==="Runtime.executionContextDestroyed") contexts.delete(message.params.executionContextId);
    if(pending.has(message.id)){
      const p=pending.get(message.id);pending.delete(message.id);clearTimeout(p.timer);
      message.error?p.reject(new Error(message.error.message)):p.resolve(message.result);
    }
  };
  function call(method,params={}) { const id=++sequence;return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error(method+" timed out"));},120000);
    pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));
  });}
  async function evaluate(contextId,expression) {
    const reply=await call("Runtime.evaluate",{contextId,expression,awaitPromise:true,returnByValue:true});
    if(reply.exceptionDetails) throw new Error(reply.exceptionDetails.exception?.description||reply.exceptionDetails.text);
    return reply.result.value;
  }
  let context;
  const run=(fn,...args)=>evaluate(context,"("+fn.toString()+")("+args.map(a=>JSON.stringify(a)).join(",")+")");
  try {
    await call("Runtime.enable");
    context=await until(async()=>{
      for(const id of contexts) {
        try {if(await evaluate(id,"typeof PDFE !== 'undefined' && typeof Asc !== 'undefined' && !!Asc.editor")) return id;}
        catch(e){if(!/context.*(find|destroy)|find.*context/i.test(e.message))throw e;}
      }
    },"PDF context missing");
    await until(()=>run(()=>Asc.editor.jf?.file?.Mp?.getInteractiveFormsInfo()?.Fields?.length===1),"Fixture field missing");
    assert.equal(await run(()=>AscDesktopEditor.LocalFileGetSourcePath()),source);
    assert.equal(await run(guid=>JSON.parse(AscDesktopEditor.GetInstallPlugins()).some(g=>(g.pluginsData||[]).some(p=>p.guid===guid)),GUID),false);
    console.log("Installing unchanged published plugin");
    assert.equal(await run(path=>AscDesktopEditor.PluginInstall(path),root+"/CAC-PDF-Signer.plugin"),true);
    await until(()=>run(guid=>PDFE.getController("Common.Controllers.Plugins").backgroundPlugins?.some(p=>p.get("guid")===guid),GUID),"Background listing missing");
    await run(guid=>{if(!Asc.editor.getUsedBackgroundPlugins().includes(guid))Asc.editor.asc_pluginRun(guid,0,"");},GUID);
    await until(()=>run(()=>Asc.editor.jf.Qd().lC.some(w=>w.type===33&&String(w.Vh).includes("onClick(f.name)"))),"Field handler did not attach");
    await delay(1500);
    console.log("Clicking the signature field in the editor");
    const clickField = async () => {
      await run(() => {
        if (typeof Asc.editor.asc_setZoom !== "function") throw new Error("Zoom harness needs updating");
        Asc.editor.asc_setZoom(50);
      });
      await delay(1000);
      const screenshot = await call("Page.captureScreenshot", {format:"png"});
      const screen = "/test/state/field-screen.png";
      fs.writeFileSync(screen, Buffer.from(screenshot.data, "base64"));
      const point = JSON.parse(cp.execFileSync("python3", ["/repo/tests/linux/field_point.py", screen], {encoding:"utf8"}));
      await call("Input.dispatchMouseEvent", {type:"mouseMoved", x:point.x, y:point.y});
      await call("Input.dispatchMouseEvent", {type:"mousePressed", x:point.x, y:point.y, button:"left", clickCount:1});
      await call("Input.dispatchMouseEvent", {type:"mouseReleased", x:point.x, y:point.y, button:"left", clickCount:1});
      report.uiClick = true;
    };
    await clickField();
    const pin=await dialog("CAC PIN");
    const workers=fs.readdirSync("/proc").filter(n=>/^\d+$/.test(n)).filter(n=>{
      try{return fs.readlinkSync("/proc/"+n+"/exe").endsWith("/native/linux-x86_64/cac-signer");}catch(_){return false;}
    });
    assert.equal(workers.length,1);
    const pid=workers[0], maps=fs.readFileSync("/proc/"+pid+"/maps","utf8");
    const executable=fs.readlinkSync("/proc/"+pid+"/exe");
    assert(maps.includes("/native/linux-x86_64/_internal/libpython3.11.so.1.0"));
    assert(maps.includes("libsofthsm2.so"));
    const uid=/^Uid:\s+(\d+)/m.exec(fs.readFileSync("/proc/"+pid+"/status","utf8"))[1];
    assert.equal(uid,"1000");
    assert(executable.includes("/onlyoffice/desktopeditors/sdkjs-plugins/"));
    report.bundledPython=true;
    report.bundledProvider = maps.includes(process.env.CAC_PKCS11_MODULE);

    type(pin,"123456");key(pin,"Return");
    const save=await dialog("Save signed PDF as");
    report.pinPrompt=true;
    const records=fs.readdirSync(recovery).filter(n=>n.endsWith(".json"));
    assert.equal(records.length,1);
    const recordPath=recovery+"/"+records[0];
    const metadata=JSON.parse(fs.readFileSync(recordPath,"utf8"));
    assert.equal(metadata.savedPath,"");
    const recoveryPath=recovery+"/"+metadata.recoveryName;
    const signedHash=digest(recoveryPath);
    report.recoveryHash=signedHash;
    assert.equal(metadata.sha256,signedHash);
    console.log("Signature created; cancelling Save As");
    key(save,"Escape");
    await until(()=>!windows("Save signed PDF as").length,"Save As did not cancel");
    await delay(1500);
    assert(!fs.existsSync(output));
    await clickField();
    const retry=await until(()=>{
      assert.equal(windows("CAC PIN").length,0,"Recovery requested a second PIN");
      return windows("Save signed PDF as")[0];
    },"Recovery Save As missing");
    assert.equal(fs.readdirSync(recovery).filter(n=>n.endsWith(".json")).length,1);
    assert.equal(digest(recoveryPath),signedHash);
    report.recoveryWithoutResigning=true;
    console.log("Saving the recovered signature to a spaced Unicode path");
    key(retry,"ctrl+l");type(retry,output);key(retry,"Return");
    await until(()=>fs.existsSync(output),"Saved PDF missing");
    await until(()=>JSON.parse(fs.readFileSync(recordPath,"utf8")).savedPath===output,"Saved state missing");
    assert.equal(digest(output),signedHash);
    assert.equal(digest(source),report.sourceHash);
    const original=fs.readFileSync(source), signed=fs.readFileSync(output);
    assert(signed.subarray(0,original.length).equals(original),"Original PDF was not preserved");
    report.originalPreserved=true;
    report.outputHash=signedHash;
    report.pdfsig=cp.execFileSync("pdfsig",["-nocert",output],{encoding:"utf8"});
    assert(report.pdfsig.includes("Signature is Valid"));
    assert(report.pdfsig.includes("InstallationTest"));
    const text=cp.execFileSync("pdftotext",["-raw",output,"-"],{encoding:"utf8"});
    for(const expected of ["TEST EXAMPLE","TEST ONLY","0000000000","Date:"]) assert(text.replace(/\\s+/g," ").includes(expected),"Appearance missing "+expected);
    report.appearanceText=text.trim();
    cp.execFileSync("pdftoppm",["-f","1","-singlefile","-r","110","-png",output,evidence+"/signed-preview"]);
    report.independentSignatureValid=true;
    report.signedFileOpened=await until(async()=>{
      const pages=await(await fetch("http://127.0.0.1:9251/json/list")).json();
      return pages.some(p=>p.url.includes("doctype=pdf") && decodeURIComponent(p.url).includes("signed validation"));
    },"Signed PDF did not reopen",30000);
    report.passed=true;
    fs.writeFileSync(evidence+"/signing-result.json",JSON.stringify(report,null,2));
    console.log("PASS: native PIN, PKCS11 signing, Save As cancellation/recovery, unchanged source, independent PDF verification and visible certificate text.");
  } finally {
    socket.close();
    for(const p of pending.values())clearTimeout(p.timer);
  }
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
