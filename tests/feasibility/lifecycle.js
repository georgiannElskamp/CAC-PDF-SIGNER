const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const assert = require("node:assert/strict");
const root = path.resolve(__dirname, "../..");
const original = fs.readFileSync(path.join(root, "plugin/native-host.js"), "utf8");
const harnessSource = fs.readFileSync(path.join(root, "tests/test_native.js"), "utf8")
  .replace("module.exports = { launchHost };", "module.exports = { harness };");

function makeHarness(source) {
  const m = {exports: {}};
  const localRequire = (name) => name === "fs" ? {
    ...fs, readFileSync: (file, ...args) => String(file).endsWith("native-host.js") ? source : fs.readFileSync(file, ...args),
  } : require(name);
  vm.runInNewContext(harnessSource, {require: localRequire, module: m, __dirname: path.join(root, "tests"),
    console, Buffer, process});
  return m.exports.harness("native-host.js");
}
function scenario(source, events) {
  const h = makeHarness(source);
  h.handlers.message({source:h.context.parent, origin:"file://",
    data:{channel:"cac-native-v1", type:"run", id:"main", request:{op:"health"}}});
  const p = h.context.process;
  let exited = false, cancelled = false;
  for (const event of events) {
    if (event === "ready") p.onprocess(0, JSON.stringify({event:"ready", version:"0.5.0"}));
    if (event === "result") p.onprocess(0, JSON.stringify({event:"result", ok:true, saved:true}));
    if (event === "noise") p.onprocess(0, "{malformed");
    if (event === "stderr") p.onprocess(1, "fixture diagnostic");
    if (event === "unload") {cancelled = true; h.handlers.unload();}
    if (event === "exit") {exited = true; p.onprocess(2, "");}
    const replies = h.sent.filter(x => x.type === "result" && x.id === "main");
    assert(replies.length <= 1, "Duplicate completion");
    assert(!replies.some(x => x.result.ok) || exited, "Success delivered before native exit");
    if (exited && !cancelled) assert(!p.ended, "Explicit end raced native cleanup");
  }
  if (events.includes("result")) assert(p.input.includes('{"op":"ack"}'), "Completed result not acknowledged");
  if (exited) assert.equal(h.sent.filter(x=>x.type==="result" && x.id==="main").length, 1);
}
function permutations(values) {
  if (!values.length) return [[]];
  return values.flatMap((x,i)=>permutations(values.filter((_,j)=>i!==j)).map(xs=>[x,...xs]));
}
const schedules = permutations(["ready","result","exit","noise","stderr"])
  .filter(s=>s.indexOf("ready")<s.indexOf("result") && s.indexOf("result")<s.indexOf("exit"));
for (const schedule of schedules) {
  scenario(original, schedule);
  scenario(original, [...schedule.slice(0,-1), "result", schedule.at(-1)]);
}
for (const schedule of [["exit"],["ready","exit"],["ready","unload","result","exit"],["unload","exit"]])
  scenario(original, schedule);
for (let i=0;i<1000;i++) {
  const noise = Array.from({length:i%11}, (_,j)=>j%2?"noise":"stderr");
  scenario(original, ["ready",...noise,"result","result","exit"]);
}
const mutants = [
  original.replace("completedResult = response;", "completedResult = response; finish(response);"),
  original.replace("if (active === process) active = null;\n          finish(completedResult", "process.end(); if (active === process) active = null;\n          finish(completedResult"),
  original.replace(/process[.]stdin[(][^;]*ack[^;]*[)];/, "void 0;"),
];
const negative = [];
for (const [index, mutant] of mutants.entries()) {
  if (mutant === original) {negative.push({index,status:"not_constructed"});continue;}
  let detected=false;
  try {scenario(mutant,["ready","result","exit"]);} catch (_) {detected=true;}
  negative.push({index,status:detected?"detected":"missed"});
}
assert(negative.every(x=>x.status==="detected"), "Known lifecycle defects were not detected");
const report={probe:"lifecycle",status:"passed",boundedOrderings:schedules.length,
  repeatedSchedules:1000,negativeControls:negative,
  limitation:"Actual host JavaScript under a fake native transport; no proof of editor C++ or physical scheduling."};
fs.mkdirSync(process.env.PROBE_REPORT,{recursive:true});
fs.writeFileSync(path.join(process.env.PROBE_REPORT,"lifecycle.json"),JSON.stringify(report,null,2));
console.log(JSON.stringify(report));
