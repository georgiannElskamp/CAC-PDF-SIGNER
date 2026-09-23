const fs=require("node:fs"), path=require("node:path"), assert=require("node:assert/strict");
const [mode,port,packagePath,reportPath]=process.argv.slice(2);
const GUID="asc.{9A58C737-A6B4-4E31-8D3F-2C940B716EF9}";
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const report={probe:"desktop-"+mode,status:"failed",mode,explicitStartCalls:0};
async function until(fn,label,ms=60000) {
  const end=Date.now()+ms;
  while(Date.now()<end){const value=await fn();if(value)return value;await pause(300);}
  throw Error(label);
}
async function main(){
  const page=await until(async()=>{
    try{return(await(await fetch("http://127.0.0.1:"+port+"/json/list",{signal:AbortSignal.timeout(2000)})).json()).find(p=>p.url.includes("doctype=pdf"));}
    catch(_){return null;}
  },"PDF editor unavailable");
  const socket=new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((yes,no)=>{socket.onopen=yes;socket.onerror=no;});
  let seq=0, context;
  const pending=new Map(), contexts=new Set();
  socket.onmessage=({data})=>{
    const m=JSON.parse(data);
    if(m.method==="Runtime.executionContextCreated")contexts.add(m.params.context.id);
    if(m.method==="Runtime.executionContextDestroyed")contexts.delete(m.params.executionContextId);
    const p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(m.error.message)):p.resolve(m.result);}
  };
  const call=(method,params={})=>new Promise((resolve,reject)=>{
    const id=++seq,timer=setTimeout(()=>{pending.delete(id);reject(Error(method+" timeout"));},70000);
    pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));
  });
  const evaluate=async(id,expression)=>{
    const r=await call("Runtime.evaluate",{contextId:id,expression,awaitPromise:true,returnByValue:true});
    if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);
    return r.result.value;
  };
  const run=(fn,...args)=>evaluate(context,"("+fn.toString()+")("+args.map(a=>JSON.stringify(a)).join(",")+")");
  const click=async p=>{
    assert(p&&p.width>0&&p.height>0,"Target is not visible");
    const x=p.x+p.width/2,y=p.y+p.height/2;
    await call("Input.dispatchMouseEvent",{type:"mousePressed",x,y,button:"left",clickCount:1});
    await call("Input.dispatchMouseEvent",{type:"mouseReleased",x,y,button:"left",clickCount:1});
    await pause(300);
  };
  const installed=()=>run(g=>JSON.parse(AscDesktopEditor.GetInstallPlugins()).some(v=>(v.pluginsData||[]).some(p=>p.guid===g)),GUID);
  const attached=()=>run(()=>!!Asc.editor?.jf?.Qd?.().lC?.some(w=>w.type===33&&String(w.Vh).includes("onClick(f.name)")));
  try{
    await call("Runtime.enable");
    context=await until(async()=>{
      for(const id of contexts){try{if(await evaluate(id,"typeof PDFE!=='undefined'&&typeof Asc!=='undefined'&&!!Asc.editor"))return id;}catch(_){}}
    },"Editor context unavailable");
    await until(()=>run(()=>Asc.editor.jf?.file?.Mp?.getInteractiveFormsInfo()?.Fields?.length===1),"Fixture not loaded");
    if(mode==="install"){
      assert.equal(await installed(),false,"Profile already has the plugin");
      assert.equal(await run(p=>AscDesktopEditor.PluginInstall(p),packagePath),true);
      report.nativeInstallation=true;
      await until(()=>run(g=>PDFE.getController("Common.Controllers.Plugins").backgroundPlugins?.some(p=>p.get("guid")===g),GUID),"No Background plugins entry");
      const tab=await run(()=>{
        const all=[...document.querySelectorAll("[data-tab],[role=tab],button,a")];
        const el=all.find(e=>(e.getAttribute("data-tab")==="plugins"||e.textContent.trim()==="Plugins")&&e.getBoundingClientRect().width>0);
        if(!el)return null;
        const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};
      });
      report.toolbarTabFound=!!tab;
      if(tab)await click(tab);
      const button=await run(()=>{
        const e=PDFE.getController("Common.Controllers.Plugins").viewPlugins.backgroundBtn.$el[0];
        const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};
      });
      await click(button);
      const toggle=await until(()=>run(g=>{
        const model=PDFE.getController("Common.Controllers.Plugins").backgroundPlugins.find(p=>p.get("guid")===g);
        const el=model.get("backgroundPlugin")?.$el.find(".plugin-toggle")[0];
        if(!el)return null;const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};
      },GUID),"Background switch not found");
      if(!await run(g=>Asc.editor.getUsedBackgroundPlugins().includes(g),GUID))await click(toggle);
      await until(attached,"Background UI activation did not attach handler");
      report.pointerEnabled=true;
      await call("Input.dispatchKeyEvent",{type:"keyDown",key:"Escape",windowsVirtualKeyCode:27});
      await call("Input.dispatchKeyEvent",{type:"keyUp",key:"Escape",windowsVirtualKeyCode:27});
      const timings=[];
      for(let i=0;i<20;i++){
        const start=Date.now();
        const result=await run(async g=>{
          const client=document.getElementById("iframe_"+g).contentWindow.CACNativeClient();
          try{return await client.call({op:"preflight"});}finally{client.close();}
        },GUID);
        assert(result.ok&&result.desktopReady&&result.recoveryWritable&&result.cardChecked===false);
        timings.push(Date.now()-start);
      }
      report.preflightOperations=timings.length;report.timingsMs=timings;
    }else{
      report.installedAfterRestart=await installed();
      report.runningInitially=await run(g=>Asc.editor.getUsedBackgroundPlugins().includes(g),GUID);
      assert(report.installedAfterRestart,"Plugin disappeared after restart");
      await until(attached,"Plugin did not resume after editor restart",45000);
      report.resumedWithoutStartCall=true;
    }
    report.status="passed";
  }catch(error){
    report.error=error.message;
    if(context)report.ui=await run(()=>[...document.querySelectorAll("[data-tab],button,a")].filter(e=>e.getBoundingClientRect().width>0)
      .map(e=>({text:e.textContent.trim().slice(0,60),tab:e.getAttribute("data-tab"),id:e.id})).slice(0,50)).catch(()=>[]);
    throw error;
  }finally{
    try{const image=await call("Page.captureScreenshot",{format:"png"});fs.writeFileSync(path.join(reportPath,"desktop-"+mode+".png"),Buffer.from(image.data,"base64"));}catch(_){}
    fs.writeFileSync(path.join(reportPath,"desktop-"+mode+".json"),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report));
    socket.close();for(const p of pending.values())clearTimeout(p.timer);
  }
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
