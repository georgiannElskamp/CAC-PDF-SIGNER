/* Independent probes for the private interfaces in the tested official editors. */
function installProbe() {
  const version = Asc.editor.GetVersion();
  const modern = version === "10.0.0" || version === "10.0.0.169";
  if (!modern && version !== "9.4.0" && version !== "9.4.0.129")
    throw new Error("The editor probe needs an interface mapping for " + version);
  const renderer = () => Asc.editor[modern ? "Ve" : "jf"];
  const reader = () => renderer()?.file?.[modern ? "Bp" : "Mp"];
  window.CACTestPdf = {
    ready: () => !!reader() && typeof renderer()[modern ? "md" : "Qd"] === "function",
    fields: () => reader()?.getInteractiveFormsInfo()?.Fields,
    widgets: () => renderer()[modern ? "md" : "Qd"]()[modern ? "TD" : "lC"],
    click: (widget) => widget[modern ? "Ml" : "Vh"],
    directory: () => AscCommon[modern ? "Qq" : "Ss"][modern ? "Xga" : "tia"],
  };
  return version;
}

module.exports = { installProbe };
