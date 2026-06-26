import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib


def copy_pixbuf_to_clipboard(pixbuf):
    """Copies a GdkPixbuf to the system clipboard (GTK4 way)."""
    try:
        display = Gdk.Display.get_default()
        clipboard = display.get_clipboard()

        # In PyGObject GTK4, Gdk.Clipboard lacks set_texture method.
        # The correct, robust approach is using Gdk.ContentProvider.
        provider = Gdk.ContentProvider.new_for_value(pixbuf)
        clipboard.set_content(provider)

        # A tiny delay or main-loop cycle is sometimes needed on Wayland
        # to ensure the clipboard owner registers before the process exits.
        context = GLib.MainContext.default()
        for _ in range(10):
            context.iteration(False)

        print("[BoomerShot] Successfully copied cropped region to clipboard.")
        return True
    except Exception as e:
        print(f"[BoomerShot] Error copying to clipboard: {e}", file=sys.stderr)
        return False
