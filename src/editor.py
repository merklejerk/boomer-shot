import os
import sys
from typing import Callable, Dict, Optional

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
from clipboard import copy_pixbuf_to_clipboard
from file_saver import save_pixbuf_to_file


class ScreenshotEditor(Gtk.Window):
    """Main window displaying the screenshot canvas and floating toolbar."""

    # Map drawing tool IDs to standard icon names for popover button synchronization
    tool_icons: Dict[str, str] = {
        TOOL_PEN: "document-edit-symbolic",
        TOOL_ARROW: "go-next-symbolic",
        TOOL_RECT: "window-maximize-symbolic",
        TOOL_BLUR: "view-conceal-symbolic",
        TOOL_TEXT: "format-text-bold-symbolic",
    }

    def __init__(self, application: Gtk.Application, mode: str, file_path: str) -> None:
        super().__init__(application=application)
        self.mode: str = mode
        self.file_path: str = file_path

        # Borderless fullscreen config
        self.set_decorated(False)
        self.fullscreen()

        # Track active tool & color
        self.active_tool: str = TOOL_PEN if mode == "window" else TOOL_SELECT

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

        # 4.5. Secure Settings Overlay
        self.config_overlay = ConfigOverlay(self)
        self.config_overlay.set_visible(False)
        overlay.add_overlay(self.config_overlay)
        # Compatibility bridge for canvas and tests
        self.api_key_overlay = self.config_overlay

        # Keyboard shortcuts (e.g. Esc to Close, Ctrl+Z to Undo, Ctrl+C to Copy, Ctrl+S to Save)
        self._setup_keybindings()

    def _create_toolbar(self):
        # The main toolbar container
        self.toolbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.toolbar_box.add_css_class("floating-toolbar")

        # --- Section 1: Selection & Cropping (only in area mode) ---
        self.tool_buttons = {}
        first_tool_btn = None

        if self.mode == "area":
            # Crop Region Button
            crop_btn = Gtk.ToggleButton()
            crop_btn.add_css_class("toolbar-btn")
            crop_btn.set_icon_name("edit-select-all-symbolic")
            crop_btn.set_tooltip_text("Crop Region")
            crop_btn.connect("toggled", self._on_tool_changed, TOOL_SELECT)
            self.tool_buttons[TOOL_SELECT] = crop_btn
            self.toolbar_box.append(crop_btn)
            first_tool_btn = crop_btn

            if self.active_tool == TOOL_SELECT:
                crop_btn.set_active(True)

            # Select Full Screen Button
            fullscreen_btn = Gtk.Button()
            fullscreen_btn.add_css_class("toolbar-btn")
            fullscreen_btn.set_icon_name("view-fullscreen-symbolic")
            fullscreen_btn.set_tooltip_text("Select Full Screen")
            fullscreen_btn.connect("clicked", lambda x: self.canvas.select_full_screen())
            self.toolbar_box.append(fullscreen_btn)

            # Separator after cropping tools
            self.toolbar_box.append(self._create_separator())

        # --- Section 2: Drawing & Markup popover group ---
        # Main markup tool button
        self.markup_menu_btn = Gtk.MenuButton()
        self.markup_menu_btn.add_css_class("toolbar-btn")
        self.markup_menu_btn.set_tooltip_text("Markup Tools")

        # Determine initial markup icon (default to PEN if active tool is not a markup tool)
        initial_tool = self.active_tool if self.active_tool in self.tool_icons else TOOL_PEN
        self.markup_menu_btn.set_icon_name(self.tool_icons[initial_tool])
        self.toolbar_box.append(self.markup_menu_btn)

        # Create Popover for drawing tools
        self.markup_popover = Gtk.Popover()
        self.markup_menu_btn.set_popover(self.markup_popover)

        popover_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        popover_box.add_css_class("popover-toolbar")
        self.markup_popover.set_child(popover_box)

        # Populate drawing tools inside popover
        markup_config = [
            (TOOL_PEN, "document-edit-symbolic", "Freehand Pen"),
            (TOOL_ARROW, "go-next-symbolic", "Draw Arrow"),
            (TOOL_RECT, "window-maximize-symbolic", "Draw Rectangle"),
            (TOOL_BLUR, "view-conceal-symbolic", "Blur / Pixelate"),
            (TOOL_TEXT, "format-text-bold-symbolic", "Add Text"),
        ]

        for tool_id, icon_name, tooltip in markup_config:
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
            popover_box.append(btn)

            # Set active state
            if tool_id == self.active_tool:
                btn.set_active(True)

        # Separator after drawing tools
        self.toolbar_box.append(self._create_separator())

        # --- Section 3: Colors popover group ---
        # Color Menu Button
        self.color_menu_btn = Gtk.MenuButton()
        self.color_menu_btn.add_css_class("toolbar-btn")
        self.color_menu_btn.set_tooltip_text("Drawing Color")
        self.toolbar_box.append(self.color_menu_btn)

        # Color indicator child widget (a small circular box)
        self.color_indicator = Gtk.Box()
        self.color_indicator.add_css_class("color-indicator-dot")
        self.color_indicator.set_valign(Gtk.Align.CENTER)
        self.color_indicator.set_halign(Gtk.Align.CENTER)
        self.color_menu_btn.set_child(self.color_indicator)

        # Create Color Popover
        self.color_popover = Gtk.Popover()
        self.color_menu_btn.set_popover(self.color_popover)

        color_popover_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        color_popover_box.add_css_class("popover-toolbar")
        self.color_popover.set_child(color_popover_box)

        # Populate colors inside popover
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

            provider = Gtk.CssProvider()
            provider.load_from_data(f"button {{ background-color: {hex_str}; }}".encode("utf-8"))
            btn.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

            btn.connect("toggled", self._on_color_changed, color_rgba, hex_str)

            if first_color_btn:
                btn.set_group(first_color_btn)
            else:
                first_color_btn = btn

            color_popover_box.append(btn)

            # Default active color is Red
            if hex_str == "#ff3b30":
                btn.set_active(True)

        # Separator after color tools
        self.toolbar_box.append(self._create_separator())

        # --- Section 4: AI Effects ---
        boomerfy_btn = Gtk.Button()
        boomerfy_btn.add_css_class("toolbar-btn")
        boomerfy_btn.set_icon_name("camera-photo-symbolic")
        boomerfy_btn.set_tooltip_text("Boomer-fy with AI")
        boomerfy_btn.connect("clicked", lambda x: self.canvas.boomerfy())
        self.toolbar_box.append(boomerfy_btn)

        config_btn = Gtk.Button()
        config_btn.add_css_class("toolbar-btn")
        config_btn.set_icon_name("view-more-symbolic")
        config_btn.set_tooltip_text("Configure BoomerShot Settings")
        config_btn.connect("clicked", lambda x: self.show_config_dialog())
        self.toolbar_box.append(config_btn)

        # Separator
        self.toolbar_box.append(self._create_separator())

        # --- Section 5: History & Undo ---
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

        # --- Section 6: Final Actions (Copy, Save, Close) ---
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

    def _create_separator(self) -> Gtk.Box:
        sep = Gtk.Box()
        sep.add_css_class("toolbar-separator")
        sep.set_size_request(1, 16)
        sep.set_valign(Gtk.Align.CENTER)
        return sep

    def _on_tool_changed(self, button: Gtk.ToggleButton, tool_id: str) -> None:
        if button.get_active():
            self.active_tool = tool_id
            self.canvas.set_tool(tool_id)

            # Update the main menu button's icon if this is a drawing tool inside popover
            if tool_id in self.tool_icons:
                self.markup_menu_btn.set_icon_name(self.tool_icons[tool_id])
                self.markup_popover.popdown()

    def _on_color_changed(self, button: Gtk.ToggleButton, color_rgba: str, hex_str: str) -> None:
        if button.get_active():
            self.canvas.set_color(color_rgba)
            self._update_color_indicator(hex_str)
            self.color_popover.popdown()

    def _update_color_indicator(self, hex_str: str) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(
            f".color-indicator-dot {{ background-color: {hex_str}; }}".encode("utf-8")
        )
        self.color_indicator.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def on_selection_completed(self) -> None:
        """Called by canvas when the crop area selection is finalized."""
        self.toolbar_container.set_visible(True)
        # Select Pen tool as default drawing option after cropping
        if TOOL_PEN in self.tool_buttons:
            self.tool_buttons[TOOL_PEN].set_active(True)

    def _send_notification(self, title: str, body: str) -> None:
        """Sends a system notification to inform the user of completed actions."""
        try:
            app = self.get_application()
            if app:
                notification = Gio.Notification.new(title)
                notification.set_body(body)
                app.send_notification("boomer-shot-notify", notification)
        except Exception as e:
            print(f"[BoomerShot] Failed to send notification: {e}", file=sys.stderr)

    def _on_copy_clicked(self) -> None:
        pixbuf = self.canvas.get_cropped_pixbuf()
        if pixbuf:
            if copy_pixbuf_to_clipboard(pixbuf):
                self._send_notification("BoomerShot", "Copied crop to clipboard!")
            self.close()
        else:
            self._send_notification("BoomerShot", "No selection made! Click & drag to crop first.")

    def _on_save_clicked(self) -> None:
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

    def _on_close_clicked(self) -> None:
        self.close()

    def _setup_keybindings(self) -> None:
        # Keyboard event controller
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

    def _on_key_pressed(
        self,
        controller: Gtk.EventControllerKey,
        keyval: int,
        keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        # Escape key hides settings overlay if visible, otherwise exits the app
        if keyval == Gdk.KEY_Escape:
            if self.config_overlay.get_visible():
                self.config_overlay.hide()
            else:
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

    def close(self) -> None:
        # Cleanup temporary raw image when editor exits
        super().close()
        try:
            if os.path.exists(self.file_path):
                os.remove(self.file_path)
        except Exception as e:
            print(f"[BoomerShot] Warning: failed to clean up temp file: {e}", file=sys.stderr)

    def show_api_key_dialog(self, on_save_callback: Optional[Callable[[], None]] = None) -> None:
        # Compatibility wrapper
        self.show_config_dialog(on_save_callback)

    def show_config_dialog(self, on_save_callback: Optional[Callable[[], None]] = None) -> None:
        self.config_overlay.show(on_save_callback)


class ConfigOverlay(Gtk.Box):
    def __init__(
        self, parent: ScreenshotEditor, on_save_callback: Optional[Callable[[], None]] = None
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.parent: ScreenshotEditor = parent
        self.on_save_callback: Optional[Callable[[], None]] = on_save_callback

        self.loaded_gemini_key: str = ""
        self.loaded_openai_key: str = ""
        self.loaded_preferred: str = "gemini"
        self.loaded_prompt: str = ""

        self.add_css_class("credentials-dialog")
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)
        self.set_size_request(440, 320)

        # Header / Title
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title_label = Gtk.Label(label="BoomerShot AI Settings")
        title_label.add_css_class("dialog-title")
        title_label.set_halign(Gtk.Align.START)
        title_box.append(title_label)
        self.append(title_box)

        # Info label
        info_label = Gtk.Label(label="Manage your AI keys and preferences.")
        info_label.add_css_class("dim-label")
        info_label.set_halign(Gtk.Align.START)
        self.append(info_label)

        # Create Notebook for tabs
        notebook = Gtk.Notebook()
        notebook.set_hexpand(True)
        notebook.set_vexpand(True)
        self.append(notebook)

        # --- Tab 1: API Keys ---
        keys_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        keys_tab.set_margin_top(12)
        keys_tab.set_margin_bottom(12)
        keys_tab.set_margin_start(12)
        keys_tab.set_margin_end(12)

        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(12)
        keys_tab.append(grid)

        # Gemini Row
        gemini_label = Gtk.Label(label="Gemini API Key:")
        gemini_label.set_halign(Gtk.Align.END)
        grid.attach(gemini_label, 0, 0, 1, 1)

        self.gemini_entry = Gtk.Entry()
        self.gemini_entry.set_visibility(False)  # hide text
        self.gemini_entry.set_hexpand(True)
        grid.attach(self.gemini_entry, 1, 0, 1, 1)

        # OpenAI Row
        openai_label = Gtk.Label(label="OpenAI API Key:")
        openai_label.set_halign(Gtk.Align.END)
        grid.attach(openai_label, 0, 1, 1, 1)

        self.openai_entry = Gtk.Entry()
        self.openai_entry.set_visibility(False)
        self.openai_entry.set_hexpand(True)
        grid.attach(self.openai_entry, 1, 1, 1, 1)

        # Preferred Provider Row
        provider_label = Gtk.Label(label="Preferred Provider:")
        provider_label.set_halign(Gtk.Align.END)
        grid.attach(provider_label, 0, 2, 1, 1)

        provider_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.gemini_radio = Gtk.CheckButton(label="Gemini")
        self.openai_radio = Gtk.CheckButton(label="OpenAI")
        self.openai_radio.set_group(self.gemini_radio)
        provider_box.append(self.gemini_radio)
        provider_box.append(self.openai_radio)
        grid.attach(provider_box, 1, 2, 1, 1)

        notebook.append_page(keys_tab, Gtk.Label(label="API Keys"))

        # --- Tab 2: AI Prompt ---
        prompt_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        prompt_tab.set_margin_top(12)
        prompt_tab.set_margin_bottom(12)
        prompt_tab.set_margin_start(12)
        prompt_tab.set_margin_end(12)

        prompt_info = Gtk.Label(label="Custom AI Image Transformation Prompt:")
        prompt_info.add_css_class("dim-label")
        prompt_info.set_halign(Gtk.Align.START)
        prompt_tab.append(prompt_info)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        self.prompt_view = Gtk.TextView()
        self.prompt_view.set_wrap_mode(Gtk.WrapMode.WORD)
        scrolled.set_child(self.prompt_view)
        prompt_tab.append(scrolled)

        notebook.append_page(prompt_tab, Gtk.Label(label="AI Prompt"))

        # Button box
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.END)
        self.append(btn_box)

        self.cancel_btn = Gtk.Button(label="Cancel")
        self.cancel_btn.connect("clicked", lambda x: self.hide())
        btn_box.append(self.cancel_btn)

        self.save_btn = Gtk.Button(label="Save")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", lambda x: self.save_keys())
        btn_box.append(self.save_btn)

        # Bind Enter key inside entries to Save action
        self.gemini_entry.connect("activate", lambda e: self.save_keys())
        self.openai_entry.connect("activate", lambda e: self.save_keys())

    def load_keys(self, on_save_callback: Optional[Callable[[], None]] = None) -> None:
        self.on_save_callback = on_save_callback

        # Disable fields until loaded
        self.gemini_entry.set_text("")
        self.openai_entry.set_text("")
        self.prompt_view.get_buffer().set_text("")
        self.gemini_entry.set_sensitive(False)
        self.openai_entry.set_sensitive(False)
        self.gemini_radio.set_sensitive(False)
        self.openai_radio.set_sensitive(False)
        self.prompt_view.set_sensitive(False)
        self.save_btn.set_sensitive(False)

        import threading

        from gi.repository import GLib

        def worker() -> None:
            from ai import get_api_key, get_custom_prompt, get_preferred_provider

            gemini_key = get_api_key("gemini") or ""
            openai_key = get_api_key("openai") or ""
            preferred = get_preferred_provider()
            prompt = get_custom_prompt()

            def update_ui() -> bool:
                self.loaded_gemini_key = gemini_key
                self.loaded_openai_key = openai_key
                self.loaded_preferred = preferred
                self.loaded_prompt = prompt

                self.gemini_entry.set_text(gemini_key)
                self.openai_entry.set_text(openai_key)
                self.prompt_view.get_buffer().set_text(prompt)
                if preferred == "openai":
                    self.openai_radio.set_active(True)
                else:
                    self.gemini_radio.set_active(True)

                self.gemini_entry.set_sensitive(True)
                self.openai_entry.set_sensitive(True)
                self.gemini_radio.set_sensitive(True)
                self.openai_radio.set_sensitive(True)
                self.prompt_view.set_sensitive(True)
                self.save_btn.set_sensitive(True)
                self.gemini_entry.grab_focus()
                return False

            GLib.idle_add(update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def show(self, on_save_callback: Optional[Callable[[], None]] = None) -> None:
        self.load_keys(on_save_callback)
        self.set_visible(True)
        self.queue_draw()
        if self.parent:
            self.parent.queue_draw()

    def hide(self) -> None:
        self.set_visible(False)
        self.queue_draw()
        if self.parent:
            self.parent.queue_draw()

    def save_keys(self) -> None:
        gemini_val = self.gemini_entry.get_text().strip()
        openai_val = self.openai_entry.get_text().strip()
        provider_val = "openai" if self.openai_radio.get_active() else "gemini"

        buffer = self.prompt_view.get_buffer()
        prompt_val = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False).strip()

        gemini_changed = gemini_val != self.loaded_gemini_key
        openai_changed = openai_val != self.loaded_openai_key
        provider_changed = provider_val != self.loaded_preferred
        prompt_changed = prompt_val != self.loaded_prompt

        if not (gemini_changed or openai_changed or provider_changed or prompt_changed):
            # Nothing changed, just hide and return
            self.hide()
            if self.on_save_callback:
                self.on_save_callback()
            return

        # Disable fields and buttons during background keyring save
        self.gemini_entry.set_sensitive(False)
        self.openai_entry.set_sensitive(False)
        self.gemini_radio.set_sensitive(False)
        self.openai_radio.set_sensitive(False)
        self.prompt_view.set_sensitive(False)
        self.save_btn.set_sensitive(False)
        self.cancel_btn.set_sensitive(False)

        import threading

        from gi.repository import GLib

        def worker() -> None:
            from ai import save_api_key, save_custom_prompt, save_preferred_provider

            error = None
            try:
                if gemini_changed:
                    save_api_key("gemini", gemini_val)
                if openai_changed:
                    save_api_key("openai", openai_val)
                if provider_changed:
                    save_preferred_provider(provider_val)
                if prompt_changed:
                    save_custom_prompt(prompt_val)
            except Exception as e:
                error = e

            def update_ui() -> bool:
                self.gemini_entry.set_sensitive(True)
                self.openai_entry.set_sensitive(True)
                self.gemini_radio.set_sensitive(True)
                self.openai_radio.set_sensitive(True)
                self.prompt_view.set_sensitive(True)
                self.save_btn.set_sensitive(True)
                self.cancel_btn.set_sensitive(True)

                if error:
                    print(f"[BoomerShot] Failed to save config: {error}")
                    if hasattr(self.parent, "_send_notification"):
                        self.parent._send_notification(
                            "BoomerShot", f"Failed to save settings: {error}"
                        )
                else:
                    self.loaded_gemini_key = gemini_val
                    self.loaded_openai_key = openai_val
                    self.loaded_preferred = provider_val
                    self.loaded_prompt = prompt_val
                    self.hide()
                    if self.on_save_callback:
                        self.on_save_callback()
                return False

            GLib.idle_add(update_ui)

        threading.Thread(target=worker, daemon=True).start()
