#!/usr/bin/env python3
import argparse
import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk

from editor import ScreenshotEditor


def apply_css():
    """Applies custom CSS from style.css for UI styling."""
    provider = Gtk.CssProvider()
    css_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "style.css")
    if os.path.exists(css_path):
        provider.load_from_path(css_path)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    else:
        print(f"[BoomerShot] Warning: stylesheet not found at {css_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="BoomerShot Screenshot & Snipping Tool Editor")
    parser.add_argument("--mode", choices=["area", "window"], required=True, help="Screenshot mode")
    parser.add_argument("--file", required=True, help="Path to raw screenshot file")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"[BoomerShot] Error: Raw screenshot file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    # Initialize Libadwaita application for modern GNOME design style
    app = Adw.Application(
        application_id="org.merklejerk.BoomerShot", flags=Gio.ApplicationFlags.FLAGS_NONE
    )

    def on_activate(application):
        apply_css()
        win = ScreenshotEditor(application, args.mode, args.file)
        win.present()

    app.connect("activate", on_activate)
    sys.exit(app.run(None))


if __name__ == "__main__":
    main()
