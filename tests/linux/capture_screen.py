"""Capture only the disposable test desktop after a GUI failure."""

import ctypes as C
import sys

gtk = C.CDLL("libgtk-3.so.0")
gdk = C.CDLL("libgdk-3.so.0")
pixbuf = C.CDLL("libgdk_pixbuf-2.0.so.0")
gobject = C.CDLL("libgobject-2.0.so.0")
gtk.gtk_init_check.argtypes = [C.c_void_p, C.c_void_p]
if not gtk.gtk_init_check(None, None):
    raise SystemExit("No display to capture")
gdk.gdk_get_default_root_window.restype = C.c_void_p
window = gdk.gdk_get_default_root_window()
gdk.gdk_window_get_width.argtypes = [C.c_void_p]
gdk.gdk_window_get_height.argtypes = [C.c_void_p]
gdk.gdk_pixbuf_get_from_window.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int, C.c_int]
gdk.gdk_pixbuf_get_from_window.restype = C.c_void_p
image = gdk.gdk_pixbuf_get_from_window(window, 0, 0, gdk.gdk_window_get_width(window), gdk.gdk_window_get_height(window))
pixbuf.gdk_pixbuf_savev.argtypes = [C.c_void_p, C.c_char_p, C.c_char_p, C.c_void_p, C.c_void_p, C.c_void_p]
try:
    if not image or not pixbuf.gdk_pixbuf_savev(image, sys.argv[1].encode(), b"png", None, None, None):
        raise RuntimeError("Could not capture the test display")
finally:
    if image:
        gobject.g_object_unref.argtypes = [C.c_void_p]
        gobject.g_object_unref(image)
