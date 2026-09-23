/* ONLYOFFICE Desktop 9.4.0 PDF adapter. */
window.CACDesktop = function (host) {
  "use strict";
  const api = host.Asc && host.Asc.editor;
  const native = host.AscDesktopEditor;
  const fingerprint = "function(){return this.jf?this.jf.vWe():null}";
  let version = "unknown";
  try {
    if (api && typeof api.GetVersion === "function") version = api.GetVersion();
  } catch (_) {}
  const pdfMode = api && typeof api.asc_getPdfProps === "function" &&
    String(api.asc_getPdfProps).replace(/\s/g, "") === fingerprint.replace(/\s/g, "");
  const formMode = api && typeof api.asc_getPdfProps === "function" &&
    String(api.asc_getPdfProps).replace(/\s/g, "") === "function(){returnnull}" &&
    typeof api.pluginMethod_GetAllForms === "function" &&
    typeof api.pluginMethod_IsFillingFormMode === "function" &&
    version === "9.4.0" &&
    host.Common && host.Common.Views && host.Common.Views.PdfSignDialog &&
    typeof host.Common.Views.PdfSignDialog.prototype.show === "function";
  if (!api || !native || (!pdfMode && !formMode)) {
    throw new Error(
      "ONLYOFFICE " + version + " needs a CAC adapter update. This plugin was tested with Desktop Editors 9.4.0.129. No document was signed.",
    );
  }
  const hooked = new Map();
  let timer;
  // Saving does not refresh the editor's original PDF stream.
  let editedSinceLoad = api.isDocumentModified();
  const onModified = () => {
    if (api.isDocumentModified()) editedSinceLoad = true;
  };
  api.asc_registerCallback("asc_onDocumentModifiedChanged", onModified);
  if (formMode) {
    const dialog = host.Common.Views.PdfSignDialog.prototype;
    let originalShow, showHandler, onAction;
    const pending = [];
    function snapshot(field) {
      if (api.isDocumentModified() || editedSinceLoad)
        throw new Error("Save your PDF form edits and reopen it before signing.");
      const forms = api.pluginMethod_GetAllForms();
      const matches = Array.isArray(forms) ? forms.filter(
        (f) => f.FormKey === field && !f.FormValue,
      ) : [];
      if (matches.length !== 1)
        throw new Error("This ONLYOFFICE signature box is filled or ambiguous.");
      const sourcePath = native.LocalFileGetSourcePath();
      if (typeof sourcePath !== "string" || !/\.pdf$/i.test(sourcePath))
        throw new Error("Save and reopen the local PDF form before signing.");
      return {
        kind: "onlyoffice-form",
        name: api.asc_getDocumentName(),
        sourcePath,
      };
    }
    function attach(onClick, onError) {
      originalShow = dialog.show;
      showHandler = function () {
        const token = { dialog: this, args: arguments, claimed: false };
        pending.push(token);
        window.setTimeout(() => {
          const index = pending.indexOf(token);
          if (index !== -1) pending.splice(index, 1);
          if (!token.claimed) originalShow.apply(token.dialog, token.args);
        }, 0);
        return this;
      };
      dialog.show = showHandler;
      onAction = (action) => {
        const token = pending[pending.length - 1];
        if (!token || !action || action.type !== 12 ||
            !api.pluginMethod_IsFillingFormMode()) return;
        try {
          const pr = action.pr;
          const formPr = pr && typeof pr.get_FormPr === "function" && pr.get_FormPr();
          const field = formPr && typeof formPr.get_Key === "function" && formPr.get_Key();
          const id = pr && typeof pr.get_InternalId === "function" && String(pr.get_InternalId());
          if (typeof field !== "string" || !field || !id) return;
          const forms = api.pluginMethod_GetAllForms();
          if (!Array.isArray(forms) || forms.filter(
            (f) => f.FormKey === field && String(f.InternalId) === id && !f.FormValue,
          ).length !== 1) return;
          token.claimed = true;
          onClick(field);
        } catch (error) {
          if (token.claimed) onError(error);
        }
      };
      api.asc_registerCallback("asc_onShowContentControlsActions", onAction);
    }
    function detach() {
      api.asc_unregisterCallback("asc_onDocumentModifiedChanged", onModified);
      if (onAction) api.asc_unregisterCallback("asc_onShowContentControlsActions", onAction);
      if (dialog.show === showHandler) dialog.show = originalShow;
      for (const token of pending) token.claimed = true;
      pending.length = 0;
    }
    return { snapshot, attach, detach };
  }
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
          doc = r.Qd();
        if (!Array.isArray(doc.lC))
          throw new Error(
            "PDF signature fields are not supported by this ONLYOFFICE build.",
          );
        const pending = doc.lC.filter((w) => w.type === 33 && !hooked.has(w));
        if (!pending.length) return;
        const forms = r.file.Mp.getInteractiveFormsInfo().Fields || [];
        for (const w of pending) {
          if (typeof w.u0 !== "function") continue;
          const appearance = w.u0();
          const f = forms.find(
            (f) => f.AP && f.AP.i === appearance,
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
