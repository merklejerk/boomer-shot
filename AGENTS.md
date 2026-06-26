# BoomerShot - AI Agent Guidelines 🤖

Welcome to the BoomerShot codebase. If you are an AI assistant working on this workspace, you must adhere to the design principles, patterns, and conventions detailed below.

---

## 📐 Project Architecture

BoomerShot is built as a hybrid application to bypass Wayland's security restrictions on screen capture:
1. **GNOME Shell Extension (Privileged):** JavaScript (ESM, GNOME 50+) located in `extension/`. Runs in-process with the window manager to capture screenshots silently and bind global hotkeys.
2. **Editor Window (User-Space):** Python 3 (GTK4 + Libadwaita + Cairo) located in `src/`. Opened fullscreen by the extension to present the annotation and cropping GUI.

```
/home/cluracan/code/boomer-shot/
├── Makefile                # Compiles schemas and installs the tool
├── README.md               # Overview and user documentation
├── AGENTS.md               # This guidelines file
├── extension/              # GNOME Shell extension code
│   ├── metadata.json       # GNOME extension metadata
│   ├── extension.js        # privileged keybinding and capture logic
│   └── schemas/            # GSettings schemas compiled in place
└── src/                    # Python GTK4 editor app
    ├── main.py             # App entrypoint and CSS loading
    ├── editor.py           # Screen layout and floating toolbar
    ├── canvas.py           # Cairo annotations & selection drawing
    ├── utils.py            # Clipboard integration & FileDialog
    └── style.css           # UI layout styling
```

---

## 🎨 Core Code Conventions & Design Rules

### 1. High-DPI and Coordinate Mappings
* **Rule:** Never store drawing coordinates in logical pixels.
* **Why:** High-DPI monitors cause physical coordinates (pixel data) to differ from logical layout coordinates.
* **Convention:**
  * Logical-to-Physical scaling is calculated dynamically as `scale = logical_size / physical_size`.
  * The Cairo context must be scaled using `ctx.scale(sx, sy)` at the start of drawing.
  * All mouse clicks/moves must be translated to the physical pixel space immediately upon capture. All shapes and point coordinate arrays must be stored in **physical coordinates**.

### 2. Wayland Clipboard Handoff
* **Rule:** Do not terminate the Python process immediately after writing to the clipboard.
* **Why:** Under Wayland, the clipboard operates on a lazy pull-model. If the copy-source process exits immediately, the target client cannot pull the image, and the copy operation is lost.
* **Convention:** Always run a tiny iteration loop of 10 cycles on the GLib main context (`GLib.MainContext.default().iteration(False)`) to allow Gdk sufficient cycles to complete the clipboard handoff before exiting the script.

### 3. Cairo-Only Image Manipulation
* **Rule:** Avoid external image processing libraries (like Pillow/PIL or OpenCV).
* **Why:** Keep the application lightweight, fast, and easy to distribute with zero binary system dependencies.
* **Convention:**
  * Image loading is done via `cairo.ImageSurface.create_from_png`.
  * Pixelation blurs are implemented by drawing the target region scaled down by a factor of 16 onto a temporary Cairo surface, and rendering it back with the `cairo.Filter.NEAREST` interpolation filter.

### 4. GTK4 Event Handling
* **Rule:** Do not use deprecated X11-style events (like `button-press-event`). Use modern GTK4 Event Controllers.
* **Convention:**
  * Mouse drags (cropping, lines, rectangles, arrows): Use `Gtk.GestureDrag`.
  * Mouse clicks (text insertions): Use `Gtk.GestureClick`.
  * Hover / Motion detection (custom cursors): Use `Gtk.EventControllerMotion`.

---

## 🛠 Command Reference

### Developer Environment Setup
* Set up the virtual environment with access to system GObject packages:
  ```bash
  make dev-setup
  ```

### Running Tests and Linters
* Run unit tests:
  ```bash
  make test
  ```
* Lint code style:
  ```bash
  make lint
  ```
* Re-format code:
  ```bash
  make format
  ```

### Compilation & Schema Setup
* Compile GSettings schemas locally:
  ```bash
  glib-compile-schemas extension/schemas/
  ```

### Installation
* Install the extension and CLI launcher:
  ```bash
  make install
  ```
  *Note: The CLI launcher is wrapped in `~/.local/bin/boomer-shot`.*

### Testing the Editor Directly
* Test the GTK4 UI directly with a sample PNG without triggering the extension:
  ```bash
  python3 src/main.py --mode area --file /path/to/some_image.png
  ```

---

## 🧪 Testing and Linting Guidelines

### Headless Drawing Verification
* **Convention:** GTK4 widget instantiation requires an active display (X11/Wayland). To prevent tests from crashing on headless hosts or remote sessions, write tests using **mock/in-memory Cairo surfaces** rather than launching GTK window loops.
* **Example:** Create a `cairo.ImageSurface` and call `annotation.draw(ctx)` to verify drawing logic.

### PyGObject Linter Exceptions (E402)
* **Convention:** Always call `gi.require_version("Gtk", "4.0")` before importing `gi.repository.Gtk`. Since this is an executable statement, Ruff flags subsequent imports as `E402` (imports not at top of file). This false positive is disabled in `pyproject.toml` and should remain ignored.

---

## 🤝 Collaboration & Communication

* **Tone:** Sobriety and wit over excessive politeness. No pandering.
* **Assistance:** Do not guess API details. Search system paths or online docs to ensure correctness.
* **Double Checks:** Always summarize concessions, hacks, and spicy workarounds during code reviews with the Tech Lead.
