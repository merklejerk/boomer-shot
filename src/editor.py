import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, Gio, Gtk

from canvas import (
    TOOL_ARROW,
    TOOL_BLUR,
    TOOL_PEN,
    TOOL_RECT,
    TOOL_SELECT,
    TOOL_TEXT,
    ScreenshotCanvas,
)
from utils import copy_pixbuf_to_clipboard, save_pixbuf_to_file


class ScreenshotEditor(Gtk.Window):
    """Main window displaying the screenshot canvas and floating toolbar."""

    def __init__(self, application, mode, file_path):
        super().__init__(application=application)
        self.mode = mode
        self.file_path = file_path

        # Borderless fullscreen config
        self.set_decorated(False)
        self.fullscreen()

        # Track active tool & color
        self.active_tool = TOOL_PEN if mode == "window" else TOOL_SELECT

        self._build_ui()

    def _build_ui(self):
        # 1. Overlay container (canvas on bottom, UI overlays on top)
        overlay = Gtk.Overlay()
        self.set_child(overlay)

        # 2. Add canvas as the main overlay base
        self.canvas = ScreenshotCanvas(self.file_path, self.mode)
        overlay.set_child(self.canvas)

        # 3. Transparent Fixed overlay for dynamic floating text inputs
        self.fixed_layout = Gtk.Fixed()
        self.fixed_layout.set_can_target(
            False
        )  # Let mouse events fall through to the canvas underneath!
        overlay.add_overlay(self.fixed_layout)
        self.canvas.fixed_container = self.fixed_layout

        # 4. Floating toolbar container (aligned at bottom center)
        self.toolbar_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toolbar_container.set_valign(Gtk.Align.END)
        self.toolbar_container.set_halign(Gtk.Align.CENTER)
        self.toolbar_container.set_margin_bottom(24)

        self._create_toolbar()
        self.toolbar_container.append(self.toolbar_box)
        overlay.add_overlay(self.toolbar_container)

        # Keyboard shortcuts (e.g. Esc to Close, Ctrl+Z to Undo, Ctrl+C to Copy, Ctrl+S to Save)
        self._setup_keybindings()

    def _create_toolbar(self):
        # The main toolbar container
        self.toolbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.toolbar_box.add_css_class("floating-toolbar")

        # --- Section 1: Drawing Tools ---
        self.tool_buttons = {}
        first_tool_btn = None

        tools_config = [
            (TOOL_PEN, "document-edit-symbolic", "Freehand Pen"),
            (TOOL_ARROW, "go-next-symbolic", "Draw Arrow"),
            (TOOL_RECT, "window-maximize-symbolic", "Draw Rectangle"),
            (TOOL_BLUR, "view-conceal-symbolic", "Blur / Pixelate"),
            (TOOL_TEXT, "format-text-bold-symbolic", "Add Text"),
        ]

        # Only add "Select Box" tool in area mode to allow redrawing the crop area
        if self.mode == "area":
            tools_config.insert(0, (TOOL_SELECT, "edit-select-all-symbolic", "Crop Region"))

        for tool_id, icon_name, tooltip in tools_config:
            btn = Gtk.ToggleButton()
            btn.add_css_class("toolbar-btn")
            btn.set_icon_name(icon_name)
            btn.set_tooltip_text(tooltip)
            btn.connect("toggled", self._on_tool_changed, tool_id)

            if first_tool_btn:
                btn.set_group(first_tool_btn)
            else:
                first_tool_btn = btn

            self.tool_buttons[tool_id] = btn
            self.toolbar_box.append(btn)

            # Set active state
            if tool_id == self.active_tool:
                btn.set_active(True)

            # Insert "Select Full Screen" right next to "Crop Region" button
            if tool_id == TOOL_SELECT:
                fullscreen_btn = Gtk.Button()
                fullscreen_btn.add_css_class("toolbar-btn")
                fullscreen_btn.set_icon_name("view-fullscreen-symbolic")
                fullscreen_btn.set_tooltip_text("Select Full Screen")
                fullscreen_btn.connect("clicked", lambda x: self.canvas.select_full_screen())
                self.toolbar_box.append(fullscreen_btn)

        # Separator
        self.toolbar_box.append(self._create_separator())

        # --- Section 2: Colors ---
        colors_config = [
            ("rgba(255, 59, 48, 1.0)", "#ff3b30", "Red"),
            ("rgba(52, 199, 89, 1.0)", "#34c759", "Green"),
            ("rgba(0, 122, 255, 1.0)", "#007aff", "Blue"),
            ("rgba(255, 204, 0, 1.0)", "#ffcc00", "Yellow"),
            ("rgba(255, 255, 255, 1.0)", "#ffffff", "White"),
            ("rgba(0, 0, 0, 1.0)", "#000000", "Black"),
        ]

        first_color_btn = None
        for color_rgba, hex_str, name in colors_config:
            btn = Gtk.ToggleButton()
            btn.add_css_class("color-btn")
            btn.set_tooltip_text(name)
            btn.set_valign(Gtk.Align.CENTER)

            # Custom inline style for button color circle
            # GTK4 allows loading custom provider for specific widgets
            provider = Gtk.CssProvider()
            provider.load_from_data(f"button {{ background-color: {hex_str}; }}".encode("utf-8"))
            btn.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

            btn.connect("toggled", self._on_color_changed, color_rgba)

            if first_color_btn:
                btn.set_group(first_color_btn)
            else:
                first_color_btn = btn

            self.toolbar_box.append(btn)

            # Default active color is Red
            if hex_str == "#ff3b30":
                btn.set_active(True)

        # Separator
        self.toolbar_box.append(self._create_separator())

        # --- Section 2.5: AI Effects ---
        boomerfy_btn = Gtk.Button()
        boomerfy_btn.add_css_class("toolbar-btn")
        boomerfy_btn.set_icon_name("camera-photo-symbolic")
        boomerfy_btn.set_tooltip_text("Boomer-fy with AI")
        boomerfy_btn.connect("clicked", lambda x: self.canvas.boomerfy())
        self.toolbar_box.append(boomerfy_btn)

        # Separator
        self.toolbar_box.append(self._create_separator())

        # --- Section 3: History & Undo ---
        undo_btn = Gtk.Button()
        undo_btn.add_css_class("toolbar-btn")
        undo_btn.set_icon_name("edit-undo-symbolic")
        undo_btn.set_tooltip_text("Undo (Ctrl+Z)")
        undo_btn.connect("clicked", lambda x: self.canvas.undo())
        self.toolbar_box.append(undo_btn)

        clear_btn = Gtk.Button()
        clear_btn.add_css_class("toolbar-btn")
        clear_btn.set_icon_name("edit-clear-all-symbolic")
        clear_btn.set_tooltip_text("Clear All")
        clear_btn.connect("clicked", lambda x: self.canvas.clear())
        self.toolbar_box.append(clear_btn)

        # Separator
        self.toolbar_box.append(self._create_separator())

        # --- Section 4: Final Actions (Copy, Save, Close) ---
        copy_btn = Gtk.Button()
        copy_btn.add_css_class("btn-success")
        copy_btn.set_icon_name("edit-copy-symbolic")
        copy_btn.set_tooltip_text("Copy to Clipboard (Ctrl+C / Enter)")
        copy_btn.connect("clicked", lambda x: self._on_copy_clicked())
        self.toolbar_box.append(copy_btn)

        save_btn = Gtk.Button()
        save_btn.add_css_class("btn-primary")
        save_btn.set_icon_name("document-save-symbolic")
        save_btn.set_tooltip_text("Save Image (Ctrl+S)")
        save_btn.connect("clicked", lambda x: self._on_save_clicked())
        self.toolbar_box.append(save_btn)

        close_btn = Gtk.Button()
        close_btn.add_css_class("btn-danger")
        close_btn.set_icon_name("window-close-symbolic")
        close_btn.set_tooltip_text("Cancel (Esc)")
        close_btn.connect("clicked", lambda x: self._on_close_clicked())
        self.toolbar_box.append(close_btn)

    def _create_separator(self):
        sep = Gtk.Box()
        sep.add_css_class("toolbar-separator")
        sep.set_size_request(1, 16)
        sep.set_valign(Gtk.Align.CENTER)
        return sep

    def _on_tool_changed(self, button, tool_id):
        if button.get_active():
            self.active_tool = tool_id
            self.canvas.set_tool(tool_id)

    def _on_color_changed(self, button, color_rgba):
        if button.get_active():
            self.canvas.set_color(color_rgba)

    def on_selection_completed(self):
        """Called by canvas when the crop area selection is finalized."""
        self.toolbar_container.set_visible(True)
        # Select Pen tool as default drawing option after cropping
        if TOOL_PEN in self.tool_buttons:
            self.tool_buttons[TOOL_PEN].set_active(True)

    def _send_notification(self, title, body):
        """Sends a system notification to inform the user of completed actions."""
        try:
            app = self.get_application()
            if app:
                notification = Gio.Notification.new(title)
                notification.set_body(body)
                app.send_notification("boomer-shot-notify", notification)
        except Exception as e:
            print(f"[BoomerShot] Failed to send notification: {e}", file=sys.stderr)

    def _on_copy_clicked(self):
        pixbuf = self.canvas.get_cropped_pixbuf()
        if pixbuf:
            if copy_pixbuf_to_clipboard(pixbuf):
                self._send_notification("BoomerShot", "Copied crop to clipboard!")
            self.close()
        else:
            self._send_notification("BoomerShot", "No selection made! Click & drag to crop first.")

    def _on_save_clicked(self):
        pixbuf = self.canvas.get_cropped_pixbuf()
        if pixbuf:
            self.set_visible(False)
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            default_filename = f"Screenshot_{timestamp}.png"
            saved_path = save_pixbuf_to_file(
                pixbuf, default_filename=default_filename, parent_window=self
            )
            if saved_path:
                self._send_notification("BoomerShot", f"Saved to {os.path.basename(saved_path)}")
                self.close()
            else:
                self.set_visible(True)
        else:
            self._send_notification("BoomerShot", "No selection made! Click & drag to crop first.")

    def _on_close_clicked(self):
        self.close()

    def _setup_keybindings(self):
        # Keyboard event controller
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        # Escape key exits the app
        if keyval == Gdk.KEY_Escape:
            self._on_close_clicked()
            return True

        # Ctrl+Z triggering Undo
        if (state & Gdk.ModifierType.CONTROL_MASK) and keyval == Gdk.KEY_z:
            self.canvas.undo()
            return True

        # Ctrl+S triggering Save
        if (state & Gdk.ModifierType.CONTROL_MASK) and keyval == Gdk.KEY_s:
            self._on_save_clicked()
            return True

        # Ctrl+C triggering Copy
        if (state & Gdk.ModifierType.CONTROL_MASK) and keyval == Gdk.KEY_c:
            self._on_copy_clicked()
            return True

        # Enter key triggers Copy (convenient shortcut)
        if keyval == Gdk.KEY_Return or keyval == Gdk.KEY_KP_Enter:
            # Only trigger copy if we are not actively typing in the text entry
            if not self.canvas.text_entry:
                self._on_copy_clicked()
                return True

        return False

    def close(self):
        # Cleanup temporary raw image when editor exits
        super().close()
        try:
            if os.path.exists(self.file_path):
                os.remove(self.file_path)
        except Exception as e:
            print(f"[BoomerShot] Warning: failed to clean up temp file: {e}", file=sys.stderr)
