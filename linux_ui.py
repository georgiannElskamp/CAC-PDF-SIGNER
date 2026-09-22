"""Native dialogs using the GTK library required by Linux ONLYOFFICE."""

import ctypes as C
from pathlib import Path


class Cancelled(Exception):
    pass


def desktop_library(name):
    # Reuse ONLYOFFICE's system GTK, rather than bundling a second desktop stack.
    return C.CDLL(name)


class Dialogs:
    def __init__(self):
        try:
            self.gtk = desktop_library("libgtk-3.so.0")
            self.glib = desktop_library("libglib-2.0.so.0")
        except OSError as exc:
            raise RuntimeError("The GTK 3 libraries required by ONLYOFFICE are unavailable.") from exc
        self.bind("gtk_init_check", C.c_int, C.c_void_p, C.c_void_p)
        if not self.gtk.gtk_init_check(None, None):
            raise RuntimeError("The signing component could not connect to the Linux desktop display.")
        for name in ("gtk_dialog_new", "gtk_entry_new"):
            self.bind(name, C.c_void_p)
        self.bind("gtk_dialog_get_content_area", C.c_void_p, C.c_void_p)
        self.bind("gtk_label_new", C.c_void_p, C.c_char_p)
        self.bind("gtk_entry_get_text", C.c_char_p, C.c_void_p)
        self.bind("gtk_entry_set_text", None, C.c_void_p, C.c_char_p)
        self.bind("gtk_dialog_add_button", C.c_void_p, C.c_void_p, C.c_char_p, C.c_int)
        self.bind("gtk_dialog_run", C.c_int, C.c_void_p)
        self.bind("gtk_dialog_set_default_response", None, C.c_void_p, C.c_int)
        self.bind("gtk_window_set_title", None, C.c_void_p, C.c_char_p)
        self.bind("gtk_window_set_default_size", None, C.c_void_p, C.c_int, C.c_int)
        self.bind("gtk_box_pack_start", None, C.c_void_p, C.c_void_p, C.c_int, C.c_int, C.c_uint)
        self.bind("gtk_container_set_border_width", None, C.c_void_p, C.c_uint)
        for name in ("gtk_window_set_modal", "gtk_window_set_keep_above", "gtk_entry_set_visibility", "gtk_entry_set_activates_default", "gtk_file_chooser_set_do_overwrite_confirmation"):
            self.bind(name, None, C.c_void_p, C.c_int)
        for name in ("gtk_widget_show_all", "gtk_widget_destroy", "gtk_widget_grab_focus", "gtk_window_present"):
            self.bind(name, None, C.c_void_p)
        self.bind("gtk_file_chooser_set_current_name", None, C.c_void_p, C.c_char_p)
        self.bind("gtk_file_chooser_set_current_folder", C.c_int, C.c_void_p, C.c_char_p)
        self.bind("gtk_file_chooser_get_filename", C.c_void_p, C.c_void_p)
        self.gtk.gtk_file_chooser_dialog_new.restype = C.c_void_p
        self.gtk.gtk_file_chooser_dialog_new.argtypes = [C.c_char_p, C.c_void_p, C.c_int, C.c_char_p]
        self.glib.g_free.argtypes = [C.c_void_p]

    def bind(self, name, result, *args):
        fn = getattr(self.gtk, name)
        fn.restype, fn.argtypes = result, list(args)

    def show(self, dialog):
        self.gtk.gtk_window_set_modal(dialog, True)
        self.gtk.gtk_window_set_keep_above(dialog, True)
        self.gtk.gtk_widget_show_all(dialog)
        self.gtk.gtk_window_present(dialog)
        return self.gtk.gtk_dialog_run(dialog)


def request_pin():
    ui = Dialogs()
    dialog = ui.gtk.gtk_dialog_new()
    entry = ui.gtk.gtk_entry_new()
    try:
        ui.gtk.gtk_window_set_title(dialog, b"CAC PIN")
        ui.gtk.gtk_window_set_default_size(dialog, 360, -1)
        content = ui.gtk.gtk_dialog_get_content_area(dialog)
        ui.gtk.gtk_container_set_border_width(content, 18)
        label = ui.gtk.gtk_label_new(b"Enter the PIN for your connected CAC.")
        ui.gtk.gtk_box_pack_start(content, label, False, False, 8)
        ui.gtk.gtk_box_pack_start(content, entry, False, False, 8)
        ui.gtk.gtk_entry_set_visibility(entry, False)
        ui.gtk.gtk_entry_set_activates_default(entry, True)
        ui.gtk.gtk_dialog_add_button(dialog, b"Cancel", -6)
        ui.gtk.gtk_dialog_add_button(dialog, b"Sign", -5)
        ui.gtk.gtk_dialog_set_default_response(dialog, -5)
        ui.gtk.gtk_widget_grab_focus(entry)
        if ui.show(dialog) != -5:
            raise Cancelled()
        pin = ui.gtk.gtk_entry_get_text(entry).decode("utf-8")
        if not pin:
            raise Cancelled()
        return pin
    finally:
        ui.gtk.gtk_entry_set_text(entry, b"")
        ui.gtk.gtk_widget_destroy(dialog)


def choose_pdf(name, folder=""):
    ui = Dialogs()
    dialog = ui.gtk.gtk_file_chooser_dialog_new(
        b"Save signed PDF as", None, 1, b"Cancel", C.c_int(-6),
        C.c_char_p(b"Save"), C.c_int(-3), C.c_void_p(),
    )
    try:
        ui.gtk.gtk_file_chooser_set_current_name(dialog, name.encode("utf-8"))
        if folder and Path(folder).is_dir():
            ui.gtk.gtk_file_chooser_set_current_folder(dialog, str(folder).encode("utf-8"))
        ui.gtk.gtk_file_chooser_set_do_overwrite_confirmation(dialog, True)
        if ui.show(dialog) != -3:
            return ""
        pointer = ui.gtk.gtk_file_chooser_get_filename(dialog)
        if not pointer:
            return ""
        try:
            filename = C.string_at(pointer).decode("utf-8")
        finally:
            ui.glib.g_free(pointer)
        return filename if Path(filename).suffix else filename + ".pdf"
    finally:
        ui.gtk.gtk_widget_destroy(dialog)
