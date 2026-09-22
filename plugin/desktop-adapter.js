/* ONLYOFFICE Desktop 9.4.0 adapter. These internal member names are guarded below.
   Source references and compatibility limits are documented in README.md. */
window.CACDesktop = function (host) {
  "use strict";
  const api = host.Asc && host.Asc.editor;
  const native = host.AscDesktopEditor;
  const fingerprint = "function(){return this.jf?this.jf.vWe():null}";
  if (
    !api ||
    !native ||
    typeof api.asc_getPdfProps !== "function" ||
    String(api.asc_getPdfProps).replace(/\s/g, "") !==
      fingerprint.replace(/\s/g, "")
  ) {
    throw new Error(
      "This ONLYOFFICE version needs a CAC adapter update. No document was signed.",
    );
  }
  const hooked = new Map();
  let timer;
  // The engine retains its original PDF stream even after an in-place save.
  // Remember edits until reload; checking only isDocumentModified() is unsafe.
  let editedSinceLoad = api.isDocumentModified();
  const onModified = () => {
    if (api.isDocumentModified()) editedSinceLoad = true;
  };
  api.asc_registerCallback("asc_onDocumentModifiedChanged", onModified);
  function renderer() {
    const r = api.jf;
    if (
      !r ||
      typeof r.Qd !== "function" ||
      !r.file ||
      !r.file.Mp ||
      typeof r.file.Mp.getInteractiveFormsInfo !== "function" ||
      typeof r.file.Mp.getFileBinary !== "function"
    )
      throw new Error("Wait for the PDF to finish opening.");
    return r;
  }
  function snapshot(field) {
    if (api.isDocumentModified() || editedSinceLoad)
      throw new Error(
        "Save your PDF edits and reopen the PDF, then click the signature box. ONLYOFFICE keeps the original PDF in memory until it is reopened.",
      );
    const r = renderer();
    const matches = (r.file.Mp.getInteractiveFormsInfo().Fields || []).filter(
      (f) => f.type === 33 && f.name === field && !f.Sig,
    );
    if (matches.length !== 1)
      throw new Error(
        "This signature field is already signed or is ambiguous.",
      );
    const bytes = new Uint8Array(r.file.Mp.getFileBinary());
    if (
      bytes.length > 40 * 1024 * 1024 ||
      String.fromCharCode(...bytes.slice(0, 5)) !== "%PDF-"
    )
      throw new Error("A PDF smaller than 40 MB is required.");
    return {
      bytes,
      name: api.asc_getDocumentName(),
      sourcePath: native.LocalFileGetSourcePath() || "",
    };
  }
  function attach(onClick, onError) {
    function scan() {
      try {
        const r = renderer(),
          doc = r.Qd(),
          forms = r.file.Mp.getInteractiveFormsInfo().Fields || [];
        if (!Array.isArray(doc.lC))
          throw new Error(
            "PDF signature fields are not supported by this ONLYOFFICE build.",
          );
        for (const w of doc.lC) {
          if (w.type !== 33 || hooked.has(w)) continue;
          const f = forms.find(
            (f) => f.AP && typeof w.u0 === "function" && f.AP.i === w.u0(),
          );
          if (!f || f.type !== 33 || f.Sig || f.display === 1 || !f.name)
            continue;
          if (
            typeof w.Cte !== "function" ||
            typeof w.Vh !== "function" ||
            !/^function\(\)\{\}$/.test(String(w.Vh).replace(/\s/g, ""))
          ) {
            throw new Error(
              "The PDF click interface changed. The CAC adapter needs an update.",
            );
          }
          const original = w.Vh;
          const handler = function () {
            original.apply(this, arguments);
            if (!w.Cte()) onClick(f.name);
          };
          w.Vh = handler;
          hooked.set(w, { original, handler });
        }
      } catch (e) {
        onError(e);
      }
    }
    scan();
    timer = window.setInterval(scan, 2000);
  }
  function detach() {
    clearInterval(timer);
    api.asc_unregisterCallback("asc_onDocumentModifiedChanged", onModified);
    for (const [w, h] of hooked) if (w.Vh === h.handler) w.Vh = h.original;
    hooked.clear();
  }
  return { snapshot, attach, detach };
};
