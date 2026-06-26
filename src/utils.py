import os
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk


def copy_pixbuf_to_clipboard(pixbuf):
    """Copies a GdkPixbuf to the system clipboard as a GdkTexture (GTK4 way)."""
    try:
        display = Gdk.Display.get_default()
        clipboard = display.get_clipboard()

        # In GTK4, clipboard image transfer uses Gdk.Texture
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        clipboard.set_texture(texture)

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


def save_pixbuf_to_file(pixbuf, default_filename="screenshot.png", parent_window=None):
    """Opens a GTK4 FileDialog to save the pixbuf, or falls back to auto-save in Pictures."""
    try:
        pictures_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        if not pictures_dir:
            pictures_dir = os.path.expanduser("~/Pictures")

        os.makedirs(pictures_dir, exist_ok=True)
        default_path = os.path.join(pictures_dir, default_filename)

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
            pixbuf.save(save_path[0], "png")
            print(f"[BoomerShot] Successfully saved screenshot to {save_path[0]}")
            return save_path[0]

    except Exception:
        # Fallback to direct auto-save if anything fails
        try:
            default_path = os.path.join(os.path.expanduser("~"), "Pictures", default_filename)
            pixbuf.save(default_path, "png")
            print(f"[BoomerShot] Fallback: Auto-saved screenshot to {default_path}")
            return default_path
        except Exception as ex:
            print(f"[BoomerShot] Critical error saving file: {ex}", file=sys.stderr)

    return None
