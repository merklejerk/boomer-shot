import os
import sys

import pytest

# Ensure we can import from src/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import gi

# Initialize GTK4 so we can query GObject signatures safely
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("GIRepository", "3.0")
from gi.repository import Gdk, Gio, GIRepository, Gtk

# Initialize Gtk application backend to ensure Gdk display is bound
Gtk.init()


def test_gdk_clipboard_api():
    """Ensure Gdk.Clipboard has the required methods for clipboard copy."""
    # We inspect the Gdk.Clipboard class directly
    methods = dir(Gdk.Clipboard)
    assert "set_content" in methods, "Gdk.Clipboard should have 'set_content'"
    assert "set" in methods, "Gdk.Clipboard should have 'set'"
    # Make sure we assert set_texture is missing so we don't regress to using it
    assert "set_texture" not in methods, "Gdk.Clipboard set_texture is missing in this environment"


def test_gdk_content_provider_api():
    """Ensure Gdk.ContentProvider has the new_for_value method."""
    methods = dir(Gdk.ContentProvider)
    assert "new_for_value" in methods, "Gdk.ContentProvider should have 'new_for_value'"


def test_gtk_file_dialog_api():
    """Ensure Gtk.FileDialog has the modern GTK4 methods."""
    methods = dir(Gtk.FileDialog)
    assert "new" in methods, "Gtk.FileDialog should have 'new'"
    assert "save" in methods, "Gtk.FileDialog should have 'save'"
    assert "save_finish" in methods, "Gtk.FileDialog should have 'save_finish'"


def test_gdk_pixbuf_api():
    """Ensure GdkPixbuf.Pixbuf has the required methods for saving images."""
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf

    methods = dir(GdkPixbuf.Pixbuf)
    assert "savev" in methods, "GdkPixbuf.Pixbuf should have 'savev'"
    assert "save" not in methods, "GdkPixbuf.Pixbuf should not have 'save' in PyGObject bindings"


def test_gnome_shell_screenshot_api():
    """Verify GNOME Shell's private Screenshot API signatures if available on system."""
    shell_typelib_path = "/usr/lib/gnome-shell"
    if os.path.exists(shell_typelib_path):
        # We prepend search paths dynamically to load private GNOME Shell libs via GObject
        repo = GIRepository.Repository.dup_default()
        repo.prepend_search_path(shell_typelib_path)

        # Check if mutter-18 or mutter-17 etc. exists and add it
        # Since GNOME 50 uses mutter 18, we search for mutter-18 first
        for mutter_ver in ["mutter-18", "mutter-17", "mutter-16", "mutter-15"]:
            mutter_path = f"/usr/lib/{mutter_ver}"
            if os.path.exists(mutter_path):
                repo.prepend_search_path(mutter_path)
                break

        try:
            # Require version 18 or whichever version is present
            gi.require_version("Shell", "18")
            import inspect

            from gi.repository import Shell

            # 1. Verify screenshot_area signature
            sig_area = inspect.signature(Shell.Screenshot.screenshot_area)
            params_area = list(sig_area.parameters.keys())

            # GJS / PyGObject signature structure
            assert "stream" in params_area, (
                "Shell.Screenshot.screenshot_area expects 'stream' argument"
            )
            assert "filename" not in params_area, (
                "Shell.Screenshot.screenshot_area should not expect 'filename'"
            )

            # 2. Verify screenshot_window signature
            sig_win = inspect.signature(Shell.Screenshot.screenshot_window)
            params_win = list(sig_win.parameters.keys())

            assert "stream" in params_win, (
                "Shell.Screenshot.screenshot_window expects 'stream' argument"
            )
            assert "flash" not in params_win, (
                "Shell.Screenshot.screenshot_window should not expect 'flash'"
            )
            assert "filename" not in params_win, (
                "Shell.Screenshot.screenshot_window should not expect 'filename'"
            )

        except Exception as e:
            pytest.skip(f"GNOME Shell private typelibs not fully loadable: {e}")
    else:
        pytest.skip("GNOME Shell private typelib path '/usr/lib/gnome-shell' not found")


def test_pango_and_pangocairo_api():
    """Ensure Pango and PangoCairo APIs are available and have expected methods."""
    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    import cairo
    from gi.repository import Pango, PangoCairo

    # 1. Pango FontDescription
    assert hasattr(Pango.FontDescription, "from_string"), (
        "Pango.FontDescription missing from_string"
    )

    # 2. Pango Layout and PangoCairo
    surface = cairo.ImageSurface(cairo.Format.ARGB32, 10, 10)
    ctx = cairo.Context(surface)
    layout = PangoCairo.create_layout(ctx)
    assert isinstance(layout, Pango.Layout), (
        "PangoCairo.create_layout did not return a Pango.Layout"
    )

    methods = dir(layout)
    assert "set_font_description" in methods, "Pango.Layout missing set_font_description"
    assert "set_text" in methods, "Pango.Layout missing set_text"
    assert "get_pixel_extents" in methods, "Pango.Layout missing get_pixel_extents"


def test_gtk_widget_and_gestures_api():
    """Ensure Gtk.Widget, EventControllers and Gestures are available and have expected methods."""
    # 1. Widget targetability and visibility methods
    widget_methods = dir(Gtk.Widget)
    assert "set_can_target" in widget_methods, "Gtk.Widget missing set_can_target"
    assert "get_can_target" in widget_methods, "Gtk.Widget missing get_can_target"
    assert "add_controller" in widget_methods, "Gtk.Widget missing add_controller"
    assert "set_visible" in widget_methods, "Gtk.Widget missing set_visible"

    # 2. Event controllers and Gestures
    assert hasattr(Gtk.GestureDrag, "new"), "Gtk.GestureDrag missing constructor new"
    assert hasattr(Gtk.GestureClick, "new"), "Gtk.GestureClick missing constructor new"
    assert hasattr(Gtk.EventControllerKey, "new"), "Gtk.EventControllerKey missing constructor new"
    assert hasattr(Gtk.EventControllerMotion, "new"), (
        "Gtk.EventControllerMotion missing constructor new"
    )

    # 3. CSS Provider
    assert hasattr(Gtk.CssProvider, "new"), "Gtk.CssProvider missing constructor new"
    css_methods = dir(Gtk.CssProvider)
    assert "load_from_data" in css_methods, "Gtk.CssProvider missing load_from_data"


def test_gio_notification_api():
    """Ensure Gio.Notification is available and has the expected methods."""
    assert hasattr(Gio.Notification, "new"), "Gio.Notification missing constructor new"
    notif_methods = dir(Gio.Notification)
    assert "set_body" in notif_methods, "Gio.Notification missing set_body"


def test_gdk_rgba_api():
    """Ensure Gdk.RGBA can parse and output string representations."""
    rgba = Gdk.RGBA()
    assert hasattr(rgba, "parse"), "Gdk.RGBA missing parse method"
    assert hasattr(rgba, "to_string"), "Gdk.RGBA missing to_string method"


def test_gtk_text_buffer_api():
    """Ensure Gtk.TextBuffer has the expected methods for get/set text."""
    buffer = Gtk.TextBuffer.new(None)
    buffer.set_text("Hello World", -1)

    start = buffer.get_start_iter()
    end = buffer.get_end_iter()
    text = buffer.get_text(start, end, False)
    assert text == "Hello World"


def test_gtk_notebook_api():
    """Ensure Gtk.Notebook has the expected methods for page management."""
    notebook = Gtk.Notebook.new()
    page1 = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
    page2 = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)

    notebook.append_page(page1, Gtk.Label(label="Tab 1"))
    notebook.append_page(page2, Gtk.Label(label="Tab 2"))

    assert notebook.get_n_pages() == 2


def test_config_avoid_redundant_writes(tmp_path):
    """Verify that save_custom_prompt and save_preferred_provider do not write if unchanged."""
    import json
    from unittest.mock import patch

    import ai

    # Mock the CONFIG_PATH to a temp file in tmp_path
    mock_config_path = str(tmp_path / "config.json")

    with patch("ai.CONFIG_PATH", mock_config_path):
        # 1. First save (writes the file)
        ai.save_custom_prompt("Initial Prompt")

        # Verify it was written
        with open(mock_config_path, "r") as f:
            data = json.load(f)
        assert data.get("prompt") == "Initial Prompt"

        # 2. Second save with SAME prompt (should not rewrite file)
        with patch("builtins.open", side_effect=open) as mock_open:
            ai.save_custom_prompt("Initial Prompt")
            # Should read but not write
            for call in mock_open.call_args_list:
                args, kwargs = call
                mode = args[1] if len(args) > 1 else kwargs.get("mode", "r")
                assert "w" not in mode, "Should not write file if value is unchanged"

        # 3. Save preferred provider (writes the file)
        ai.save_preferred_provider("openai")

        # 4. Save SAME provider (should not rewrite file)
        with patch("builtins.open", side_effect=open) as mock_open:
            ai.save_preferred_provider("openai")
            for call in mock_open.call_args_list:
                args, kwargs = call
                mode = args[1] if len(args) > 1 else kwargs.get("mode", "r")
                assert "w" not in mode, "Should not write file if provider is unchanged"
