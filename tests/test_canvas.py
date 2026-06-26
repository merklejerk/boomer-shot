import os
import sys

import cairo
import gi
import pytest

# Ensure we can import from src/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk

from canvas import ArrowAnnotation, BlurAnnotation, PenAnnotation, RectAnnotation, TextAnnotation


@pytest.fixture
def cairo_context():
    """Provides an in-memory Cairo context for headless testing."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 200)
    return cairo.Context(surface)


@pytest.fixture
def active_color():
    color = Gdk.RGBA()
    color.parse("rgba(255, 59, 48, 1.0)")
    return color


def test_pen_annotation(cairo_context, active_color):
    pen = PenAnnotation(active_color, line_width=4.0)
    pen.points = [(10, 10), (20, 20), (30, 15)]

    # Verify properties
    assert pen.color == active_color
    assert pen.line_width == 4.0

    # Assert drawing completes without crash on headless Cairo context
    pen.draw(cairo_context)


def test_rect_annotation(cairo_context, active_color):
    rect = RectAnnotation(active_color, line_width=2.0, x1=10, y1=20, x2=50, y2=80)

    assert rect.x1 == 10
    assert rect.y1 == 20
    assert rect.x2 == 50
    assert rect.y2 == 80

    # Assert drawing completes without crash
    rect.draw(cairo_context)


def test_arrow_annotation(cairo_context, active_color):
    arrow = ArrowAnnotation(active_color, line_width=4.0, x1=10, y1=10, x2=100, y2=100)

    assert arrow.x1 == 10
    assert arrow.x2 == 100

    # Assert drawing completes without crash
    arrow.draw(cairo_context)


def test_blur_annotation(cairo_context):
    # Create mock background surface
    bg_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 100, 100)

    blur = BlurAnnotation(x1=10, y1=10, x2=50, y2=50, bg_surface=bg_surface)
    assert blur.x1 == 10
    assert blur.bg_surface == bg_surface

    # Assert drawing completes without crash
    blur.draw(cairo_context)


def test_text_annotation(cairo_context, active_color):
    text_ann = TextAnnotation(active_color, x=15, y=30, text="Hello BoomerShot")

    assert text_ann.text == "Hello BoomerShot"
    assert text_ann.x == 15

    # Assert drawing completes without crash
    # Note: Text annotation relies on Pango, which is supported on headless servers
    # if standard fontconfig fonts are available.
    try:
        text_ann.draw(cairo_context)
    except Exception as e:
        pytest.fail(f"Pango text drawing crashed: {e}")


def test_coordinate_mapping_logic():
    """Verify coordinate transformation scales correctly (equivalent to _logical_to_physical)."""
    # Suppose logical canvas is 960x540 and background physical screenshot is 1920x1080 (2x scaling)
    logical_w, logical_h = 960, 540
    img_w, img_h = 1920, 1080

    scale_x = logical_w / img_w
    scale_y = logical_h / img_h

    # Convert a click at (480, 270) logical
    click_lx, click_ly = 480, 270

    px = click_lx / scale_x
    py = click_ly / scale_y

    # Should correspond to physical center (960, 540)
    assert px == 960.0
    assert py == 540.0
