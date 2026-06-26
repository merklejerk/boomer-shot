import os
import sys
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib, Gtk


def save_pixbuf_to_file(
    pixbuf: GdkPixbuf.Pixbuf,
    default_filename: str = "screenshot.png",
    parent_window: Optional[Gtk.Window] = None,
) -> Optional[str]:
    """Opens a GTK4 FileDialog to save the pixbuf, or falls back to auto-save in Pictures."""
    try:
        pictures_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        if not pictures_dir:
            pictures_dir = os.path.expanduser("~/Pictures")

        os.makedirs(pictures_dir, exist_ok=True)

        # In GTK4, Gtk.FileChooserDialog is deprecated. We use Gtk.FileDialog!
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Save Screenshot")
        dialog.set_initial_name(default_filename)

        # Set initial folder
        initial_file = Gio.File.new_for_path(pictures_dir)
        dialog.set_initial_folder(initial_file)

        # We want to run this synchronously or handle callbacks.
        # Since GTK4 file dialog is async, we'll run a nested main loop to block until saved,
        # keeping the code flow straightforward.
        loop = GLib.MainLoop()
        save_path = [None]

        def on_save_callback(dialog_obj, result):
            try:
                target_file = dialog_obj.save_finish(result)
                if target_file:
                    save_path[0] = target_file.get_path()
            except Exception as ex:
                print(f"[BoomerShot] File dialog error or cancelled: {ex}", file=sys.stderr)
            loop.quit()

        dialog.save(parent_window, None, on_save_callback)
        loop.run()

        if save_path[0]:
            pixbuf.savev(save_path[0], "png", [], [])
            print(f"[BoomerShot] Successfully saved screenshot to {save_path[0]}")
            return save_path[0]

    except Exception:
        # Fallback to direct auto-save if anything fails
        try:
            default_path = os.path.join(os.path.expanduser("~"), "Pictures", default_filename)
            pixbuf.savev(default_path, "png", [], [])
            print(f"[BoomerShot] Fallback: Auto-saved screenshot to {default_path}")
            return default_path
        except Exception as ex:
            print(f"[BoomerShot] Critical error saving file: {ex}", file=sys.stderr)

    return None
