import math

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk, Pango, PangoCairo

# Tools definition
TOOL_SELECT = "select"
TOOL_PEN = "pen"
TOOL_ARROW = "arrow"
TOOL_RECT = "rect"
TOOL_BLUR = "blur"
TOOL_TEXT = "text"


class Annotation:
    """Base class for annotations."""

    def __init__(self, color, line_width):
        self.color = color  # Gdk.RGBA
        self.line_width = line_width

    def draw(self, ctx):
        pass


class PenAnnotation(Annotation):
    def __init__(self, color, line_width):
        super().__init__(color, line_width)
        self.points = []

    def draw(self, ctx):
        if len(self.points) < 2:
            return
        ctx.save()
        ctx.set_source_rgba(self.color.red, self.color.green, self.color.blue, self.color.alpha)
        ctx.set_line_width(self.line_width)
        ctx.set_line_cap(cairo.LineCap.ROUND)
        ctx.set_line_join(cairo.LineJoin.ROUND)

        ctx.move_to(self.points[0][0], self.points[0][1])
        for p in self.points[1:]:
            ctx.line_to(p[0], p[1])
        ctx.stroke()
        ctx.restore()


class RectAnnotation(Annotation):
    def __init__(self, color, line_width, x1, y1, x2, y2):
        super().__init__(color, line_width)
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2

    def draw(self, ctx):
        ctx.save()
        ctx.set_source_rgba(self.color.red, self.color.green, self.color.blue, self.color.alpha)
        ctx.set_line_width(self.line_width)

        x = min(self.x1, self.x2)
        y = min(self.y1, self.y2)
        w = abs(self.x2 - self.x1)
        h = abs(self.y2 - self.y1)

        ctx.rectangle(x, y, w, h)
        ctx.stroke()
        ctx.restore()


class ArrowAnnotation(Annotation):
    def __init__(self, color, line_width, x1, y1, x2, y2):
        super().__init__(color, line_width)
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2

    def draw(self, ctx):
        ctx.save()
        ctx.set_source_rgba(self.color.red, self.color.green, self.color.blue, self.color.alpha)
        ctx.set_line_width(self.line_width)
        ctx.set_line_cap(cairo.LineCap.ROUND)

        # Main line
        ctx.move_to(self.x1, self.y1)
        ctx.line_to(self.x2, self.y2)
        ctx.stroke()

        # Arrow head
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        angle = math.atan2(dy, dx)
        arrow_len = max(15, self.line_width * 3)
        arrow_angle = math.pi / 6  # 30 degrees

        ctx.move_to(self.x2, self.y2)
        ctx.line_to(
            self.x2 - arrow_len * math.cos(angle - arrow_angle),
            self.y2 - arrow_len * math.sin(angle - arrow_angle),
        )
        ctx.line_to(
            self.x2 - arrow_len * math.cos(angle + arrow_angle),
            self.y2 - arrow_len * math.sin(angle + arrow_angle),
        )
        ctx.close_path()
        ctx.fill()
        ctx.restore()


class BlurAnnotation(Annotation):
    def __init__(self, x1, y1, x2, y2, bg_surface):
        # Blur has no color or line_width
        super().__init__(None, 0)
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.bg_surface = bg_surface

    def draw(self, ctx):
        x = min(self.x1, self.x2)
        y = min(self.y1, self.y2)
        w = abs(self.x2 - self.x1)
        h = abs(self.y2 - self.y1)

        if w < 2 or h < 2:
            return

        ctx.save()

        # Pixelation scale factor
        pixel_scale = 16
        sw = max(1, int(w / pixel_scale))
        sh = max(1, int(h / pixel_scale))

        # Create a small surface to scale down the pixels
        small_surface = cairo.ImageSurface(cairo.Format.ARGB32, sw, sh)
        small_ctx = cairo.Context(small_surface)

        # Draw the background surface shifted and scaled down
        small_ctx.scale(1.0 / pixel_scale, 1.0 / pixel_scale)
        small_ctx.set_source_surface(self.bg_surface, -x, -y)
        small_ctx.paint()

        # Draw the small surface back onto the main canvas, scaled up with NEAREST filter
        ctx.translate(x, y)
        ctx.scale(pixel_scale, pixel_scale)

        pattern = cairo.SurfacePattern(small_surface)
        pattern.set_filter(cairo.Filter.NEAREST)

        ctx.set_source(pattern)
        ctx.rectangle(0, 0, w / pixel_scale, h / pixel_scale)
        ctx.fill()
        ctx.restore()


class TextAnnotation(Annotation):
    def __init__(self, color, x, y, text):
        # Fixed line width for font drawing scaling
        super().__init__(color, 24)
        self.x, self.y = x, y
        self.text = text

    def draw(self, ctx):
        if not self.text:
            return
        ctx.save()
        ctx.set_source_rgba(self.color.red, self.color.green, self.color.blue, self.color.alpha)

        # Use Pango to render text cleanly in GTK
        layout = PangoCairo.create_layout(ctx)
        font_desc = Pango.FontDescription.from_string("Outfit Bold 18")
        layout.set_font_description(font_desc)
        layout.set_text(self.text, -1)

        # Position and draw
        ctx.move_to(
            self.x, self.y - 12
        )  # adjust slightly upward so cursor click is roughly baseline
        PangoCairo.show_layout(ctx, layout)
        ctx.restore()


class ScreenshotCanvas(Gtk.DrawingArea):
    """Custom drawing area for screenshot, selection box, and annotations."""

    def __init__(self, file_path, mode):
        super().__init__()
        self.file_path = file_path
        self.mode = mode

        # Load screenshot into Cairo ImageSurface
        self.bg_surface = cairo.ImageSurface.create_from_png(file_path)
        self.img_w = self.bg_surface.get_width()
        self.img_h = self.bg_surface.get_height()

        # Selection coordinates (physical pixels)
        if mode == "window":
            # In window mode, the whole image is selected
            self.crop_x1 = 0
            self.crop_y1 = 0
            self.crop_x2 = self.img_w
            self.crop_y2 = self.img_h
            self.selection_made = True
            self.current_tool = TOOL_PEN
        else:
            self.crop_x1 = 0
            self.crop_y1 = 0
            self.crop_x2 = 0
            self.crop_y2 = 0
            self.selection_made = False
            self.current_tool = TOOL_SELECT

        # Color & Stroke config
        self.active_color = Gdk.RGBA()
        self.active_color.parse("rgba(255, 59, 48, 1.0)")  # red default
        self.active_line_width = 4.0

        # Annotation states
        self.annotations = []
        self.undo_stack = []
        self.current_annotation = None

        # Drag gesture variables
        self.drag_start_x = 0
        self.drag_start_y = 0

        # Set up DrawingArea
        self.set_draw_func(self._on_draw)

        # Text input controller
        self.fixed_container = None  # Set by editor
        self.text_entry = None

        # Event controllers
        self._setup_events()

    def _setup_events(self):
        # 1. Drag controller (for crop box drawing & annotation strokes)
        self.drag_gesture = Gtk.GestureDrag.new()
        self.drag_gesture.connect("drag-begin", self._on_drag_begin)
        self.drag_gesture.connect("drag-update", self._on_drag_update)
        self.drag_gesture.connect("drag-end", self._on_drag_end)
        self.add_controller(self.drag_gesture)

        # 2. Click controller (specifically for text click trigger)
        self.click_gesture = Gtk.GestureClick.new()
        self.click_gesture.connect("pressed", self._on_clicked)
        self.add_controller(self.click_gesture)

    def set_tool(self, tool):
        self._commit_text_entry()
        self.current_tool = tool
        if tool == TOOL_SELECT:
            self.selection_made = False
            self.crop_x1 = self.crop_y1 = self.crop_x2 = self.crop_y2 = 0
            self.annotations = []  # clear annotations when re-selecting
        self.queue_draw()

    def set_color(self, color_str):
        self._commit_text_entry()
        self.active_color.parse(color_str)

    def undo(self):
        self._commit_text_entry()
        if self.annotations:
            self.undo_stack.append(self.annotations.pop())
            self.queue_draw()

    def clear(self):
        self._commit_text_entry()
        if self.annotations:
            self.annotations = []
            self.undo_stack = []
            self.queue_draw()

    def _get_scale(self):
        """Returns the logical-to-physical scale factor for rendering."""
        lw = self.get_width()
        lh = self.get_height()
        if lw == 0 or lh == 0:
            return 1.0, 1.0
        return lw / self.img_w, lh / self.img_h

    def _logical_to_physical(self, lx, ly):
        sx, sy = self._get_scale()
        return lx / sx, ly / sy

    def _on_draw(self, area, ctx, w, h):
        # Scale drawing context to match screen logical size to image physical size
        sx, sy = self._get_scale()
        ctx.scale(sx, sy)

        # 1. Draw the background screenshot
        ctx.set_source_surface(self.bg_surface, 0, 0)
        ctx.paint()

        # 2. Draw crop/selection overlay in area mode
        if self.mode == "area":
            self._draw_selection_overlay(ctx)

        # 3. Clip drawings to the crop rectangle if selection is made
        if self.selection_made:
            ctx.save()
            cx = min(self.crop_x1, self.crop_x2)
            cy = min(self.crop_y1, self.crop_y2)
            cw = abs(self.crop_x2 - self.crop_x1)
            ch = abs(self.crop_y2 - self.crop_y1)

            # Clip drawing to only the active crop box
            ctx.rectangle(cx, cy, cw, ch)
            ctx.clip()

            # Draw finalized annotations
            for ann in self.annotations:
                ann.draw(ctx)

            # Draw active annotation currently being dragged
            if self.current_annotation:
                self.current_annotation.draw(ctx)

            ctx.restore()

        return True

    def _draw_selection_overlay(self, ctx):
        cx = min(self.crop_x1, self.crop_x2)
        cy = min(self.crop_y1, self.crop_y2)
        cw = abs(self.crop_x2 - self.crop_x1)
        ch = abs(self.crop_y2 - self.crop_y1)

        # Draw a semi-transparent dark shade over the whole screen
        ctx.save()
        ctx.set_source_rgba(0.0, 0.0, 0.0, 0.5)
        ctx.rectangle(0, 0, self.img_w, self.img_h)
        ctx.fill()

        # Cut out the selected crop box so it's fully bright/clear
        if cx != 0 or cy != 0 or cw != 0 or ch != 0:
            ctx.set_operator(cairo.Operator.CLEAR)
            ctx.rectangle(cx, cy, cw, ch)
            ctx.fill()

            # Draw selection border
            ctx.set_operator(cairo.Operator.OVER)
            ctx.set_source_rgba(0.0, 0.48, 1.0, 1.0)  # clean blue border
            ctx.set_line_width(2.0)
            ctx.rectangle(cx, cy, cw, ch)
            ctx.stroke()

        ctx.restore()

    def _on_drag_begin(self, gesture, start_x, start_y):
        self._commit_text_entry()
        self.drag_start_x, self.drag_start_y = self._logical_to_physical(start_x, start_y)

        if self.current_tool == TOOL_SELECT:
            self.selection_made = False
            self.crop_x1, self.crop_y1 = self.drag_start_x, self.drag_start_y
            self.crop_x2, self.crop_y2 = self.drag_start_x, self.drag_start_y
        elif self.selection_made:
            # Check if dragging starts inside the cropped box
            cx = min(self.crop_x1, self.crop_x2)
            cy = min(self.crop_y1, self.crop_y2)
            cw = abs(self.crop_x2 - self.crop_x1)
            ch = abs(self.crop_y2 - self.crop_y1)

            if (cx <= self.drag_start_x <= cx + cw) and (cy <= self.drag_start_y <= cy + ch):
                # Spawn active annotation based on tool selection
                if self.current_tool == TOOL_PEN:
                    self.current_annotation = PenAnnotation(
                        self.active_color, self.active_line_width
                    )
                    self.current_annotation.points.append((self.drag_start_x, self.drag_start_y))
                elif self.current_tool == TOOL_RECT:
                    self.current_annotation = RectAnnotation(
                        self.active_color,
                        self.active_line_width,
                        self.drag_start_x,
                        self.drag_start_y,
                        self.drag_start_x,
                        self.drag_start_y,
                    )
                elif self.current_tool == TOOL_ARROW:
                    self.current_annotation = ArrowAnnotation(
                        self.active_color,
                        self.active_line_width,
                        self.drag_start_x,
                        self.drag_start_y,
                        self.drag_start_x,
                        self.drag_start_y,
                    )
                elif self.current_tool == TOOL_BLUR:
                    self.current_annotation = BlurAnnotation(
                        self.drag_start_x,
                        self.drag_start_y,
                        self.drag_start_x,
                        self.drag_start_y,
                        self.bg_surface,
                    )
        self.queue_draw()

    def _on_drag_update(self, gesture, offset_x, offset_y):
        sx, sy = self._get_scale()
        p_offset_x = offset_x / sx
        p_offset_y = offset_y / sy
        curr_x = self.drag_start_x + p_offset_x
        curr_y = self.drag_start_y + p_offset_y

        if self.current_tool == TOOL_SELECT:
            self.crop_x2, self.crop_y2 = curr_x, curr_y
        elif self.current_annotation:
            if self.current_tool == TOOL_PEN:
                self.current_annotation.points.append((curr_x, curr_y))
            elif self.current_tool in (TOOL_RECT, TOOL_ARROW, TOOL_BLUR):
                self.current_annotation.x2 = curr_x
                self.current_annotation.y2 = curr_y
        self.queue_draw()

    def _on_drag_end(self, gesture, offset_x, offset_y):
        if self.current_tool == TOOL_SELECT:
            # Finalize crop box
            cw = abs(self.crop_x2 - self.crop_x1)
            ch = abs(self.crop_y2 - self.crop_y1)

            if cw > 5 and ch > 5:
                self.selection_made = True
                # Switch to drawing mode immediately
                self.current_tool = TOOL_PEN
                self.get_root().on_selection_completed()

            else:
                self.selection_made = False
                self.crop_x1 = self.crop_y1 = self.crop_x2 = self.crop_y2 = 0
        elif self.current_annotation:
            self.annotations.append(self.current_annotation)
            self.undo_stack = []  # Clear redo stack on new action
            self.current_annotation = None

        self.queue_draw()

    def _on_clicked(self, gesture, n_press, lx, ly):
        self._commit_text_entry()
        if not self.selection_made or self.current_tool != TOOL_TEXT:
            return

        px, py = self._logical_to_physical(lx, ly)

        # Verify click is inside selection
        cx = min(self.crop_x1, self.crop_x2)
        cy = min(self.crop_y1, self.crop_y2)
        cw = abs(self.crop_x2 - self.crop_x1)
        ch = abs(self.crop_y2 - self.crop_y1)

        if not ((cx <= px <= cx + cw) and (cy <= py <= cy + ch)):
            return

        # Create overlay text entry widget at the clicked logical coordinates
        self.text_entry = Gtk.Entry()
        self.text_entry.add_css_class("floating-text-input")
        self.text_entry.set_size_request(200, -1)

        # Save logical/physical mapping coordinates on widget
        self.text_entry.px = px
        self.text_entry.py = py

        # Put in layout container
        self.fixed_container.put(self.text_entry, lx, ly)
        self.text_entry.grab_focus()

        # Commit text on Enter key press
        self.text_entry.connect("activate", lambda widget: self._commit_text_entry())

    def _commit_text_entry(self):
        """Reads text from entry widget, saves it as TextAnnotation, and cleans up entry widget."""
        if not self.text_entry:
            return

        text = self.text_entry.get_text().strip()
        px = self.text_entry.px
        py = self.text_entry.py

        if text:
            # We clone active color so future color changes don't affect this text retrospectively
            cloned_color = Gdk.RGBA()
            cloned_color.parse(self.active_color.to_string())

            ann = TextAnnotation(cloned_color, px, py, text)
            self.annotations.append(ann)
            self.undo_stack = []

        self.fixed_container.remove(self.text_entry)
        self.text_entry = None
        self.queue_draw()

    def get_cropped_pixbuf(self):
        """Renders the crop region with annotations into a GdkPixbuf and returns it."""
        self._commit_text_entry()

        cx = int(min(self.crop_x1, self.crop_x2))
        cy = int(min(self.crop_y1, self.crop_y2))
        cw = int(abs(self.crop_x2 - self.crop_x1))
        ch = int(abs(self.crop_y2 - self.crop_y1))

        if cw <= 0 or ch <= 0:
            return None

        # Draw selection content onto a temporary ImageSurface
        export_surface = cairo.ImageSurface(cairo.Format.ARGB32, cw, ch)
        export_ctx = cairo.Context(export_surface)

        # Draw background screenshot shifted
        export_ctx.set_source_surface(self.bg_surface, -cx, -cy)
        export_ctx.paint()

        # Apply crop shift and draw annotations
        export_ctx.translate(-cx, -cy)
        for ann in self.annotations:
            ann.draw(export_ctx)

        # Convert cairo surface to GdkPixbuf
        # To do this cleanly, we write surface data to a stream or convert bytes
        # Fortunately, Gdk.pixbuf_get_from_texture and Gdk.Texture.new_for_pixbuf are available.
        # But we can also save to a temp PNG in memory and load via Pixbuf, which is bulletproof!
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as temp:
            export_surface.write_to_png(temp.name)
            from gi.repository import GdkPixbuf

            pixbuf = GdkPixbuf.Pixbuf.new_from_file(temp.name)
            return pixbuf
