import math
import sys

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
        pixel_scale = 8
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
        self.drag_action = None
        self.initial_crop_x1 = 0
        self.initial_crop_y1 = 0
        self.initial_crop_x2 = 0
        self.initial_crop_y2 = 0

        self.ai_loading = False
        self.ai_loading_text = ""

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

        # 3. Motion controller (for hover cursor updates)
        self.motion_controller = Gtk.EventControllerMotion.new()
        self.motion_controller.connect("motion", self._on_motion)
        self.add_controller(self.motion_controller)

    def set_tool(self, tool):
        self._commit_text_entry()
        self.current_tool = tool
        if tool == TOOL_SELECT:
            self.selection_made = False
            self.crop_x1 = self.crop_y1 = self.crop_x2 = self.crop_y2 = 0
            self.annotations = []
            self.undo_stack = []
            if self.mode == "area":
                root = self.get_root()
                if root and hasattr(root, "toolbar_container"):
                    root.toolbar_container.set_visible(False)
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

    def select_full_screen(self):
        self._commit_text_entry()
        self.crop_x1 = 0
        self.crop_y1 = 0
        self.crop_x2 = self.img_w
        self.crop_y2 = self.img_h
        self.selection_made = True
        root = self.get_root()
        if root and hasattr(root, "on_selection_completed"):
            root.on_selection_completed()
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

        # 4. Draw AI Loading overlay if active
        if getattr(self, "ai_loading", False):
            ctx.save()
            # Draw translucent dark overlay over the entire drawing area
            ctx.set_source_rgba(0.08, 0.08, 0.08, 0.75)
            ctx.rectangle(0, 0, self.img_w, self.img_h)
            ctx.fill()

            # Draw a beautiful loading pill capsule in the center
            layout = PangoCairo.create_layout(ctx)
            font_desc = Pango.FontDescription.from_string("Outfit Bold 18")
            layout.set_font_description(font_desc)
            layout.set_text(self.ai_loading_text, -1)

            _, logical_rect = layout.get_pixel_extents()
            text_w = logical_rect.width
            text_h = logical_rect.height

            tx = (self.img_w - text_w) / 2
            ty = (self.img_h - text_h) / 2

            ctx.set_source_rgba(0.12, 0.12, 0.12, 0.9)
            padding_x = 32
            padding_y = 16
            rx = tx - padding_x
            ry = ty - padding_y
            rw = text_w + 2 * padding_x
            rh = text_h + 2 * padding_y

            radius = 16
            ctx.new_sub_path()
            ctx.arc(rx + rw - radius, ry + radius, radius, -math.pi / 2, 0)
            ctx.arc(rx + rw - radius, ry + rh - radius, radius, 0, math.pi / 2)
            ctx.arc(rx + radius, ry + rh - radius, radius, math.pi / 2, math.pi)
            ctx.arc(rx + radius, ry + radius, radius, math.pi, 3 * math.pi / 2)
            ctx.close_path()
            ctx.fill()

            # Accent line on pill
            ctx.set_source_rgba(0.0, 0.48, 1.0, 1.0)
            ctx.set_line_width(2.0)
            ctx.new_sub_path()
            ctx.arc(rx + rw - radius, ry + radius, radius, -math.pi / 2, 0)
            ctx.arc(rx + rw - radius, ry + rh - radius, radius, 0, math.pi / 2)
            ctx.arc(rx + radius, ry + rh - radius, radius, math.pi / 2, math.pi)
            ctx.arc(rx + radius, ry + radius, radius, math.pi, 3 * math.pi / 2)
            ctx.close_path()
            ctx.stroke()

            # Draw text
            ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
            ctx.move_to(tx, ty)
            PangoCairo.show_layout(ctx, layout)

            ctx.restore()

        return True

    def _draw_selection_overlay(self, ctx):
        cx = min(self.crop_x1, self.crop_x2)
        cy = min(self.crop_y1, self.crop_y2)
        cw = abs(self.crop_x2 - self.crop_x1)
        ch = abs(self.crop_y2 - self.crop_y1)

        ctx.save()
        ctx.set_source_rgba(0.0, 0.0, 0.0, 0.5)

        # Draw dark overlay only outside the crop area (avoiding Operator.CLEAR completely)
        if cx == 0 and cy == 0 and cw == 0 and ch == 0:
            ctx.rectangle(0, 0, self.img_w, self.img_h)
            ctx.fill()
        else:
            # 1. Top rect
            if cy > 0:
                ctx.rectangle(0, 0, self.img_w, cy)
            # 2. Bottom rect
            if cy + ch < self.img_h:
                ctx.rectangle(0, cy + ch, self.img_w, self.img_h - (cy + ch))
            # 3. Left rect
            if cx > 0:
                ctx.rectangle(0, cy, cx, ch)
            # 4. Right rect
            if cx + cw < self.img_w:
                ctx.rectangle(cx + cw, cy, self.img_w - (cx + cw), ch)
            ctx.fill()

            # Draw selection border
            ctx.set_source_rgba(0.0, 0.48, 1.0, 1.0)  # clean blue border
            ctx.set_line_width(2.0)
            ctx.rectangle(cx, cy, cw, ch)
            ctx.stroke()

            # Draw corner resize handles if a selection exists
            if self.selection_made:
                ctx.set_source_rgba(0.0, 0.48, 1.0, 1.0)
                handle_r = 6.0  # handle radius
                for hx, hy in [(cx, cy), (cx + cw, cy), (cx, cy + ch), (cx + cw, cy + ch)]:
                    ctx.arc(hx, hy, handle_r, 0, 2 * math.pi)
                    ctx.fill()
                    ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
                    ctx.set_line_width(1.5)
                    ctx.arc(hx, hy, handle_r, 0, 2 * math.pi)
                    ctx.stroke()
                    ctx.set_source_rgba(0.0, 0.48, 1.0, 1.0)

        if (
            cx == 0
            and cy == 0
            and cw == 0
            and ch == 0
            and self.mode == "area"
            and not self.selection_made
        ):
            # Draw a beautiful pill capsule with help guide text in the center
            layout = PangoCairo.create_layout(ctx)
            font_desc = Pango.FontDescription.from_string("Outfit Bold 16")
            layout.set_font_description(font_desc)
            layout.set_text("Click & drag to select crop area  •  Esc to cancel", -1)

            # Get text dimensions to center it
            _, logical_rect = layout.get_pixel_extents()
            text_w = logical_rect.width
            text_h = logical_rect.height

            # Center coordinates (in user space coordinates, which maps to physical pixels)
            tx = (self.img_w - text_w) / 2
            ty = (self.img_h - text_h) / 2

            # Capsule background
            ctx.set_operator(cairo.Operator.OVER)
            ctx.set_source_rgba(0.08, 0.08, 0.08, 0.85)

            padding_x = 24
            padding_y = 12
            rx = tx - padding_x
            ry = ty - padding_y
            rw = text_w + 2 * padding_x
            rh = text_h + 2 * padding_y

            radius = 12
            ctx.new_sub_path()
            ctx.arc(rx + rw - radius, ry + radius, radius, -math.pi / 2, 0)
            ctx.arc(rx + rw - radius, ry + rh - radius, radius, 0, math.pi / 2)
            ctx.arc(rx + radius, ry + rh - radius, radius, math.pi / 2, math.pi)
            ctx.arc(rx + radius, ry + radius, radius, math.pi, 3 * math.pi / 2)
            ctx.close_path()
            ctx.fill()

            # Draw white text
            ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
            ctx.move_to(tx, ty)
            PangoCairo.show_layout(ctx, layout)

        ctx.restore()

    def _on_drag_begin(self, gesture, start_x, start_y):
        if getattr(self, "ai_loading", False):
            return
        self._commit_text_entry()
        self.drag_start_x, self.drag_start_y = self._logical_to_physical(start_x, start_y)
        print(
            f"[BoomerShot] Drag begin: logical ({start_x:.1f}, {start_y:.1f}), "
            f"physical ({self.drag_start_x:.1f}, {self.drag_start_y:.1f})"
        )
        self.drag_action = None

        if self.selection_made:
            # Check distances to corners for resizing (active in all tools)
            threshold = 20  # physical pixels
            dist_tl = math.hypot(self.drag_start_x - self.crop_x1, self.drag_start_y - self.crop_y1)
            dist_tr = math.hypot(self.drag_start_x - self.crop_x2, self.drag_start_y - self.crop_y1)
            dist_bl = math.hypot(self.drag_start_x - self.crop_x1, self.drag_start_y - self.crop_y2)
            dist_br = math.hypot(self.drag_start_x - self.crop_x2, self.drag_start_y - self.crop_y2)

            if dist_tl < threshold:
                self.drag_action = "resize_tl"
            elif dist_tr < threshold:
                self.drag_action = "resize_tr"
            elif dist_bl < threshold:
                self.drag_action = "resize_bl"
            elif dist_br < threshold:
                self.drag_action = "resize_br"

        if self.drag_action in ("resize_tl", "resize_tr", "resize_bl", "resize_br"):
            # Resizing selection
            pass
        elif self.current_tool == TOOL_SELECT:
            if self.selection_made:
                if (
                    self.crop_x1 <= self.drag_start_x <= self.crop_x2
                    and self.crop_y1 <= self.drag_start_y <= self.crop_y2
                ):
                    self.drag_action = "move"
                    self.initial_crop_x1 = self.crop_x1
                    self.initial_crop_y1 = self.crop_y1
                    self.initial_crop_x2 = self.crop_x2
                    self.initial_crop_y2 = self.crop_y2
                else:
                    self.drag_action = "create"
                    self.selection_made = False
                    self.crop_x1 = self.crop_x2 = self.drag_start_x
                    self.crop_y1 = self.crop_y2 = self.drag_start_y
                    self.annotations = []  # clear annotations when starting a brand new crop region
                    self.undo_stack = []
            else:
                self.drag_action = "create"
                self.selection_made = False
                self.crop_x1 = self.crop_x2 = self.drag_start_x
                self.crop_y1 = self.crop_y2 = self.drag_start_y
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
        print(
            f"[BoomerShot] Drag update: offset ({offset_x:.1f}, {offset_y:.1f}) -> "
            f"current ({curr_x:.1f}, {curr_y:.1f})"
        )

        if self.drag_action is not None:
            if not self.selection_made or self.drag_action == "create":
                self.crop_x2, self.crop_y2 = curr_x, curr_y
            elif self.drag_action == "move":
                dx = curr_x - self.drag_start_x
                dy = curr_y - self.drag_start_y
                cw = self.initial_crop_x2 - self.initial_crop_x1
                ch = self.initial_crop_y2 - self.initial_crop_y1

                # Constrain within bounds
                new_x1 = max(0, min(self.img_w - cw, self.initial_crop_x1 + dx))
                new_y1 = max(0, min(self.img_h - ch, self.initial_crop_y1 + dy))
                self.crop_x1 = new_x1
                self.crop_y1 = new_y1
                self.crop_x2 = new_x1 + cw
                self.crop_y2 = new_y1 + ch
            elif self.drag_action == "resize_tl":
                self.crop_x1 = max(0, min(self.crop_x2 - 10, curr_x))
                self.crop_y1 = max(0, min(self.crop_y2 - 10, curr_y))
            elif self.drag_action == "resize_tr":
                self.crop_x2 = max(self.crop_x1 + 10, min(self.img_w, curr_x))
                self.crop_y1 = max(0, min(self.crop_y2 - 10, curr_y))
            elif self.drag_action == "resize_bl":
                self.crop_x1 = max(0, min(self.crop_x2 - 10, curr_x))
                self.crop_y2 = max(self.crop_y1 + 10, min(self.img_h, curr_y))
            elif self.drag_action == "resize_br":
                self.crop_x2 = max(self.crop_x1 + 10, min(self.img_w, curr_x))
                self.crop_y2 = max(self.crop_y1 + 10, min(self.img_h, curr_y))
        elif self.current_annotation:
            if self.current_tool == TOOL_PEN:
                self.current_annotation.points.append((curr_x, curr_y))
            elif self.current_tool in (TOOL_RECT, TOOL_ARROW, TOOL_BLUR):
                self.current_annotation.x2 = curr_x
                self.current_annotation.y2 = curr_y
        self.queue_draw()

    def _on_drag_end(self, gesture, offset_x, offset_y):
        print(f"[BoomerShot] Drag end: offset ({offset_x:.1f}, {offset_y:.1f})")
        if self.drag_action is not None:
            # Finalize crop box
            x1 = min(self.crop_x1, self.crop_x2)
            x2 = max(self.crop_x1, self.crop_x2)
            y1 = min(self.crop_y1, self.crop_y2)
            y2 = max(self.crop_y1, self.crop_y2)
            self.crop_x1, self.crop_x2 = x1, x2
            self.crop_y1, self.crop_y2 = y1, y2

            cw = self.crop_x2 - self.crop_x1
            ch = self.crop_y2 - self.crop_y1

            if cw > 5 and ch > 5:
                self.selection_made = True
                # Switch to drawing mode immediately only on initial creation
                if self.drag_action == "create":
                    self.current_tool = TOOL_PEN
                    self.get_root().on_selection_completed()
            else:
                self.selection_made = False
                self.crop_x1 = self.crop_y1 = self.crop_x2 = self.crop_y2 = 0

            self.drag_action = None
        elif self.current_annotation:
            self.annotations.append(self.current_annotation)
            self.undo_stack = []  # Clear redo stack on new action
            self.current_annotation = None

        self.queue_draw()

    def _update_cursor(self, cursor_name):
        try:
            if cursor_name:
                cursor = Gdk.Cursor.new_from_name(cursor_name, None)
                self.set_cursor(cursor)
            else:
                self.set_cursor(None)
        except Exception as e:
            print(f"[BoomerShot] Failed to set cursor {cursor_name}: {e}", file=sys.stderr)

    def _on_motion(self, controller, lx, ly):
        if getattr(self, "ai_loading", False):
            self._update_cursor(None)
            return
        if not self.selection_made:
            if self.current_tool == TOOL_SELECT:
                self._update_cursor("crosshair")
            else:
                self._update_cursor(None)
            return

        px, py = self._logical_to_physical(lx, ly)

        # Corners
        threshold = 20
        dist_tl = math.hypot(px - self.crop_x1, py - self.crop_y1)
        dist_tr = math.hypot(px - self.crop_x2, py - self.crop_y1)
        dist_bl = math.hypot(px - self.crop_x1, py - self.crop_y2)
        dist_br = math.hypot(px - self.crop_x2, py - self.crop_y2)

        if dist_tl < threshold:
            self._update_cursor("nwse-resize")
        elif dist_tr < threshold:
            self._update_cursor("nesw-resize")
        elif dist_bl < threshold:
            self._update_cursor("nesw-resize")
        elif dist_br < threshold:
            self._update_cursor("nwse-resize")
        elif (
            self.current_tool == TOOL_SELECT
            and self.crop_x1 <= px <= self.crop_x2
            and self.crop_y1 <= py <= self.crop_y2
        ):
            self._update_cursor("move")
        else:
            if self.current_tool == TOOL_SELECT:
                self._update_cursor("crosshair")
            else:
                self._update_cursor(None)

    def _on_clicked(self, gesture, n_press, lx, ly):
        if getattr(self, "ai_loading", False):
            return
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
        if self.fixed_container:
            self.fixed_container.set_can_target(True)
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

        if self.fixed_container:
            self.fixed_container.remove(self.text_entry)
            self.fixed_container.set_can_target(False)
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

    def boomerfy(self):
        """Triggers the background thread to run the boomerfy pipeline."""
        import threading

        from gi.repository import GLib

        # Check if keys are configured in a background thread to prevent
        # blocking the main thread if keyring is locked
        def check_worker():
            from ai import get_api_key

            gemini_key = get_api_key("gemini")
            openai_key = get_api_key("openai")

            def on_check_completed():
                if not gemini_key and not openai_key:
                    root = self.get_root()
                    if root and hasattr(root, "show_api_key_dialog"):
                        root.show_api_key_dialog(on_save_callback=self.boomerfy)
                else:
                    self._run_boomerfy_pipeline()
                return False

            GLib.idle_add(on_check_completed)

        threading.Thread(target=check_worker, daemon=True).start()

    def _run_boomerfy_pipeline(self):
        pixbuf = self.get_cropped_pixbuf()
        if not pixbuf:
            # If no selection is made, we automatically select the full screen
            self.select_full_screen()
            pixbuf = self.get_cropped_pixbuf()

        if not pixbuf:
            return

        import os
        import tempfile
        import threading

        from gi.repository import GLib

        # Save current cropped selection to a temp file
        fd, temp_in_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        pixbuf.savev(temp_in_path, "png", [], [])

        self.ai_loading = True
        self.ai_loading_text = "AI is Boomer-fying your screenshot..."
        self.queue_draw()

        def worker():
            from ai import boomerfy_image

            try:
                new_img_path = boomerfy_image(temp_in_path)

                # Cleanup input temp file
                try:
                    os.remove(temp_in_path)
                except Exception:
                    pass

                def update_ui():
                    try:
                        import cairo

                        new_bg = cairo.ImageSurface.create_from_png(new_img_path)
                        self.bg_surface = new_bg
                        self.img_w = new_bg.get_width()
                        self.img_h = new_bg.get_height()

                        # Reset crop selection to full screen
                        self.crop_x1 = 0
                        self.crop_y1 = 0
                        self.crop_x2 = self.img_w
                        self.crop_y2 = self.img_h
                        self.selection_made = True

                        # Clear existing annotations
                        self.annotations = []
                        self.undo_stack = []

                        self.ai_loading = False
                        self.queue_draw()

                        # Cleanup generated temp file
                        try:
                            os.remove(new_img_path)
                        except Exception:
                            pass

                        # Notify editor window
                        root = self.get_root()
                        if root:
                            if hasattr(root, "on_selection_completed"):
                                root.on_selection_completed()
                            if hasattr(root, "_send_notification"):
                                root._send_notification(
                                    "BoomerShot", "Screenshot successfully boomer-fied! 👴"
                                )
                    except Exception as e:
                        self.ai_loading = False
                        self.queue_draw()
                        print(
                            f"[BoomerShot] Error updating canvas with AI image: {e}",
                            file=sys.stderr,
                        )
                        root = self.get_root()
                        if root and hasattr(root, "_send_notification"):
                            root._send_notification("BoomerShot", f"Failed to load AI image: {e}")

                GLib.idle_add(update_ui)

            except Exception as ex:
                err_msg = str(ex)
                # Cleanup input temp file
                try:
                    os.remove(temp_in_path)
                except Exception:
                    pass

                def update_error():
                    self.ai_loading = False
                    self.queue_draw()
                    print(f"[BoomerShot] AI Boomerfy failed: {err_msg}", file=sys.stderr)
                    root = self.get_root()
                    if root and hasattr(root, "_send_notification"):
                        root._send_notification("BoomerShot", f"AI Boomerfy failed: {err_msg}")

                GLib.idle_add(update_error)

        threading.Thread(target=worker, daemon=True).start()
