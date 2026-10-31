/* ONLYOFFICE Desktop PDF adapters; fingerprints bind private interfaces to tested builds. */
window.CACDesktop = function (host) {
  "use strict";
  const api = host.Asc && host.Asc.editor;
  const native = host.AscDesktopEditor;
  const profiles = [
    { versions: ["9.4.0", "9.4.0.129"], fingerprint: "function(){returnthis.jf?this.jf.vWe():null}",
      renderer: "jf", document: "Qd", reader: "Mp", widgets: "lC", appearance: "u0",
      filled: "Cte", click: "Vh", urls: "Ss", directory: "tia" },
    { versions: ["10.0.0", "10.0.0.169"], fingerprint: "function(){returnthis.Ve?this.Ve.tMe():null}",
      renderer: "Ve", document: "md", reader: "Bp", widgets: "TD", appearance: "ZT",
      filled: "Ufb", click: "Ml", urls: "Qq", directory: "Xga" },
  ];
  let version = "unknown";
  try {
    if (api && typeof api.GetVersion === "function") version = api.GetVersion();
  } catch (_) {}
  const signature = api && typeof api.asc_getPdfProps === "function" &&
    String(api.asc_getPdfProps).replace(/\s/g, "");
  const pdfProfile = profiles.find((p) => p.fingerprint === signature);
  const profile = pdfProfile || profiles.find((p) => p.versions.includes(version));
  const pdfMode = !!pdfProfile;
  const formMode = api && typeof api.asc_getPdfProps === "function" &&
    String(api.asc_getPdfProps).replace(/\s/g, "") === "function(){returnnull}" &&
    typeof api.pluginMethod_GetAllForms === "function" &&
    typeof api.pluginMethod_IsFillingFormMode === "function" &&
    profile && profile.versions.includes(version) &&
    typeof host.AscCommon?.[profile.urls]?.[profile.directory] === "string" &&
    typeof native?.loadLocalFile === "function" &&
    host.Common && host.Common.Views && host.Common.Views.PdfSignDialog &&
    typeof host.Common.Views.PdfSignDialog.prototype.show === "function";
  if (!api || !native || (!pdfMode && !formMode)) {
    throw new Error(
      "ONLYOFFICE " + version + " needs a CAC adapter update. Supported interfaces: Desktop Editors 9.4.0.129 and 10.0.0.169. No document was signed.",
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
    function sourcePath() {
      const path = native.LocalFileGetSourcePath();
      if (typeof path !== "string" || !/\.pdf$/i.test(path))
        throw new Error("Save and reopen the local PDF form before signing.");
      return path;
    }
    function state(field) {
      if (api.isDocumentModified() || editedSinceLoad)
        throw new Error("Save your PDF form edits and reopen it before signing.");
      if (!api.pluginMethod_IsFillingFormMode())
        throw new Error("Switch the PDF form to Preview mode before signing.");
      const forms = api.pluginMethod_GetAllForms();
      const matches = Array.isArray(forms) ? forms.filter(
        (f) => f.FormKey === field && !f.FormValue,
      ) : [];
      if (matches.length !== 1 || matches[0].InternalId == null)
        throw new Error("This ONLYOFFICE signature box is filled or ambiguous.");
      return {
        sourcePath: sourcePath(),
        directory: host.AscCommon[profile.urls][profile.directory],
        name: api.asc_getDocumentName(),
        id: String(matches[0].InternalId),
      };
    }
    function same(a, b) {
      return a.sourcePath === b.sourcePath && a.directory === b.directory &&
        a.name === b.name && a.id === b.id;
    }
    function filePath(url) {
      if (url.protocol !== "file:" || url.search || url.hash || url.username || url.password)
        throw new Error("The editor's recovery location is unsupported.");
      const path = decodeURIComponent(url.pathname.replace(/%(?![0-9a-fA-F]{2})/g, "%25"));
      if (/[\0\r\n]/.test(path))
        throw new Error("The editor's recovery location is invalid.");
      if (/^\/[A-Za-z]:\//.test(path))
        return path.slice(1).replace(/\//g, "\\");
      if (url.hostname && /^Win/i.test(host.navigator?.platform || ""))
        return "\\\\" + url.hostname + path.replace(/\//g, "\\");
      if (url.hostname)
        throw new Error("The editor's recovery location is unsupported.");
      if (!path.startsWith("/"))
        throw new Error("The editor's recovery location is invalid.");
      return path;
    }
    function recoveryFile(directory, name) {
      const base = new URL(directory.endsWith("/") ? directory : directory + "/");
      return filePath(new URL(encodeURIComponent(name), base));
    }
    function load(path) {
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("The editor's recovery copy could not be read.")), 10000);
        try {
          native.loadLocalFile(path, (value) => {
            clearTimeout(timeout);
            if (!value || (typeof value.length !== "number" &&
                !(value instanceof ArrayBuffer)))
              reject(new Error("The editor's recovery copy is missing."));
            else resolve(new Uint8Array(value));
          });
        } catch (error) {
          clearTimeout(timeout);
          reject(error);
        }
      });
    }
    function fileName(bytes, sourcePath) {
      if (bytes.length > 4096) throw new Error("The editor's recovery metadata is too large.");
      const xml = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      if (/<!/i.test(xml)) throw new Error("The editor's recovery metadata is invalid.");
      const doc = new DOMParser().parseFromString(xml, "application/xml");
      const info = doc.documentElement;
      const name = info?.getAttribute("name");
      if (info?.tagName !== "info" || info.getAttribute("type") !== "87" ||
          doc.getElementsByTagName("parsererror").length ||
          typeof name !== "string" || !/\.pdf$/i.test(name) ||
          name === "." || name === ".." || /[\/\0\r\n]/.test(name) ||
          (/^(?:[A-Za-z]:[\\/]|\\\\)/.test(sourcePath) && /[\\:]/.test(name)))
        throw new Error("The editor's recovery metadata is invalid.");
      return name;
    }
    async function snapshot(field) {
      const identity = state(field);
      const name = fileName(await load(recoveryFile(identity.directory, "asc_name.info")),
        identity.sourcePath);
      if (!same(identity, state(field)) || name !== identity.name)
        throw new Error("The active PDF form changed. Reopen it before signing.");
      const bytes = await load(recoveryFile(identity.directory, name));
      if (!same(identity, state(field)) || bytes.length > 40 * 1024 * 1024 ||
          String.fromCharCode(...bytes.slice(0, 5)) !== "%PDF-")
        throw new Error("The active PDF form changed or its recovery copy is invalid.");
      return { kind: "onlyoffice-form", bytes, name, sourcePath: identity.sourcePath, identity };
    }
    function stillCurrent(source, field) {
      try { return same(source.identity, state(field)); }
      catch (_) { return false; }
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
        if (!token || !action || action.type !== 12) return;
        let filling;
        try {
          filling = api.pluginMethod_IsFillingFormMode();
        } catch (error) {
          token.claimed = true;
          onError(error);
          return;
        }
        if (!filling) return;
        token.claimed = true;
        try {
          const pr = action.pr;
          const formPr = pr && typeof pr.get_FormPr === "function" && pr.get_FormPr();
          const field = formPr && typeof formPr.get_Key === "function" && formPr.get_Key();
          const id = pr && typeof pr.get_InternalId === "function" && String(pr.get_InternalId());
          if (typeof field !== "string" || !field || !id)
            throw new Error("The ONLYOFFICE signature box could not be identified.");
          const forms = api.pluginMethod_GetAllForms();
          if (!Array.isArray(forms) || forms.filter(
            (f) => f.FormKey === field && String(f.InternalId) === id && !f.FormValue,
          ).length !== 1)
            throw new Error("This ONLYOFFICE signature box is filled or ambiguous.");
          onClick(field);
        } catch (error) {
          onError(error);
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
    return { snapshot, attach, detach, stillCurrent };
  }
  function renderer() {
    const r = api[profile.renderer];
    if (
      !r ||
      typeof r[profile.document] !== "function" ||
      !r.file ||
      !r.file[profile.reader] ||
      typeof r.file[profile.reader].getInteractiveFormsInfo !== "function" ||
      typeof r.file[profile.reader].getFileBinary !== "function"
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
    const matches = (r.file[profile.reader].getInteractiveFormsInfo().Fields || []).filter(
      (f) => f.type === 33 && f.name === field && !f.Sig,
    );
    if (matches.length !== 1)
      throw new Error(
        "This signature field is already signed or is ambiguous.",
      );
    const bytes = new Uint8Array(r.file[profile.reader].getFileBinary());
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
          doc = r[profile.document]();
        if (!Array.isArray(doc[profile.widgets]))
          throw new Error(
            "PDF signature fields are not supported by this ONLYOFFICE build.",
          );
        const pending = doc[profile.widgets].filter((w) => w.type === 33 && !hooked.has(w));
        if (!pending.length) return;
        const forms = r.file[profile.reader].getInteractiveFormsInfo().Fields || [];
        for (const w of pending) {
          if (typeof w[profile.appearance] !== "function") continue;
          const appearance = w[profile.appearance]();
          const f = forms.find(
            (f) => f.AP && f.AP.i === appearance,
          );
          if (!f || f.type !== 33 || f.Sig || f.display === 1 || !f.name)
            continue;
          if (
            typeof w[profile.filled] !== "function" ||
            typeof w[profile.click] !== "function" ||
            !/^function\(\)\{\}$/.test(String(w[profile.click]).replace(/\s/g, ""))
          ) {
            throw new Error(
              "The PDF click interface changed. The CAC adapter needs an update.",
            );
          }
          const original = w[profile.click];
          const handler = function () {
            original.apply(this, arguments);
            if (!w[profile.filled]()) onClick(f.name);
          };
          w[profile.click] = handler;
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
    for (const [w, h] of hooked) if (w[profile.click] === h.handler) w[profile.click] = h.original;
    hooked.clear();
  }
  return { snapshot, attach, detach };
};
