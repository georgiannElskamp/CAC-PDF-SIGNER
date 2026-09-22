"""Windows Save As dialog."""

import ctypes
import json
import sys
from ctypes import wintypes


def check_desktop():
    if sys.platform == "linux":
        from linux_ui import Dialogs

        Dialogs()
    elif sys.platform == "win32":
        ctypes.WinDLL("comdlg32", use_last_error=True)
    else:
        raise RuntimeError("This package supports Windows and Linux desktop editors.")


def choose_pdf(name, folder=""):
    if sys.platform == "linux":
        from linux_ui import choose_pdf as linux_choose_pdf

        return linux_choose_pdf(name, folder)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    dialogs = ctypes.WinDLL("comdlg32", use_last_error=True)
    hook_type = ctypes.WINFUNCTYPE(
        ctypes.c_size_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )

    class OpenFileName(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", hook_type),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", ctypes.c_void_p),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND

    class NotifyHeader(ctypes.Structure):
        _fields_ = [
            ("hwndFrom", wintypes.HWND),
            ("idFrom", ctypes.c_size_t),
            ("code", wintypes.UINT),
        ]

    @hook_type
    def show_on_top(hwnd, message, _wparam, _lparam):
        ready = (
            message == 0x004E
            and _lparam
            and ctypes.cast(_lparam, ctypes.POINTER(NotifyHeader)).contents.code
            == (0x100000000 - 601)
        )
        if (
            ready
        ):  # CDN_INITDONE: position/raise after Windows finishes creating the dialog.
            dialog = user32.GetParent(hwnd) or hwnd
            user32.SetWindowPos(dialog, wintypes.HWND(-1), 0, 0, 0, 0, 0x43)
            user32.SetForegroundWindow(dialog)
        return 0

    filename = ctypes.create_unicode_buffer(name, 32768)
    params = OpenFileName()
    params.lStructSize = ctypes.sizeof(params)
    # Associate the dialog with its editor, so it cannot hide behind that window.
    document_name = (
        name[:-11] + ".pdf" if name.lower().endswith("-signed.pdf") else name
    )
    params.hwndOwner = user32.FindWindowW(None, document_name + " - ONLYOFFICE")
    params.lpstrFilter = "PDF files (*.pdf)\0*.pdf\0\0"
    params.nFilterIndex = 1
    params.lpstrFile = ctypes.cast(filename, wintypes.LPWSTR)
    params.nMaxFile = len(filename)
    params.lpstrInitialDir = folder or None
    params.lpstrTitle = "Save signed PDF as"
    params.lpstrDefExt = "pdf"
    # Explorer, enable hook, overwrite confirmation, existing folder, no chdir.
    params.Flags = 0x80000 | 0x20 | 0x2 | 0x800 | 0x8
    params.lpfnHook = show_on_top
    dialogs.GetSaveFileNameW.argtypes = [ctypes.POINTER(OpenFileName)]
    dialogs.GetSaveFileNameW.restype = wintypes.BOOL
    if dialogs.GetSaveFileNameW(ctypes.byref(params)):
        return filename.value
    error = dialogs.CommDlgExtendedError()
    if error:
        raise RuntimeError(
            f"Windows could not open Save As (error {error}). Click the signature box to retry; your signed copy is retained."
        )
    return ""


if __name__ == "__main__":
    try:
        print(
            json.dumps(
                {
                    "path": choose_pdf(
                        sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""
                    )
                }
            )
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
