import os
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk


def copy_pixbuf_to_clipboard(pixbuf):
    """Copies a GdkPixbuf to the system clipboard (GTK4 way)."""
    try:
        display = Gdk.Display.get_default()
        clipboard = display.get_clipboard()

        # In PyGObject GTK4, Gdk.Clipboard lacks set_texture method.
        # The correct, robust approach is using Gdk.ContentProvider.
        provider = Gdk.ContentProvider.new_for_value(pixbuf)
        clipboard.set_content(provider)

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


def boomerfy_image(input_image_path):
    """Boomer-fies the screenshot using either Gemini (native image-to-image via gpt-image-2/Imagen)

    or OpenAI (native image-to-image via gpt-image-2 with vision+DALL-E 3 fallback).
    """
    import base64
    import io
    import os
    import tempfile

    import requests
    from PIL import Image

    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not gemini_key and not openai_key:
        raise ValueError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is set in environment.")

    # Read the input image bytes
    with open(input_image_path, "rb") as f:
        image_bytes = f.read()

    new_image_bytes = None

    if gemini_key:
        print("[BoomerShot] Using Gemini native image-to-image model...")
        from google import genai
        from google.genai.types import GenerateContentConfig, Modality

        client = genai.Client(api_key=gemini_key)

        # Load image via PIL for the SDK
        pil_image = Image.open(io.BytesIO(image_bytes))

        prompt = (
            "Generate a new image based on this screenshot. Style it to look exactly like a "
            "low-quality photo taken by a cringey boomer on a phone camera pointed at a "
            "monitor screen. The photo must have a visible moiré pattern, dust, reflections "
            "of a messy room on the monitor glass, and a strong camera flash glare in the "
            "center of the screen."
        )

        try:
            # Let's try gemini-2.5-flash-image
            response = client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[pil_image, prompt],
                config=GenerateContentConfig(
                    response_modalities=[Modality.TEXT, Modality.IMAGE],
                ),
            )
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    new_image_bytes = part.inline_data.data
                    break
        except Exception as e:
            print(f"[BoomerShot] gemini-2.5-flash-image failed, trying gemini-3.1-flash-image: {e}")
            try:
                response = client.models.generate_content(
                    model="gemini-3.1-flash-image",
                    contents=[pil_image, prompt],
                    config=GenerateContentConfig(
                        response_modalities=[Modality.TEXT, Modality.IMAGE],
                    ),
                )
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        new_image_bytes = part.inline_data.data
                        break
            except Exception as e2:
                # If both fail, let's try the description-based pipeline
                print(
                    "[BoomerShot] gemini-3.1-flash-image failed, "
                    f"falling back to description + text-to-image: {e2}"
                )
                desc_response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        pil_image,
                        (
                            "Describe the contents of this screenshot in extreme detail, "
                            "including UI text, controls, window placement, colors, and layout, "
                            "so that it can be completely recreated. Keep it descriptive."
                        ),
                    ],
                )
                description = desc_response.text

                boomer_prompt = (
                    "A photo taken on a cheap, low-quality smartphone camera pointed at "
                    f"a computer screen. The screen displays: {description}. The photo "
                    "is slightly blurry, has visible RGB subpixels, moiré patterns, screen "
                    "glare from the camera flash in the center, reflection of a messy room "
                    "on the monitor glass, and is slightly tilted and off-center."
                )

                try:
                    response_img = client.models.generate_content(
                        model="gemini-2.5-flash-image",
                        contents=boomer_prompt,
                        config=GenerateContentConfig(
                            response_modalities=[Modality.TEXT, Modality.IMAGE],
                        ),
                    )
                    for part in response_img.candidates[0].content.parts:
                        if part.inline_data:
                            new_image_bytes = part.inline_data.data
                            break
                except Exception:
                    response_img = client.models.generate_images(
                        model="imagen-3.0-generate-002",
                        prompt=boomer_prompt,
                        config=dict(number_of_images=1, output_mime_type="image/png"),
                    )
                    new_image_bytes = response_img.generated_images[0].image.image_bytes

        if not new_image_bytes:
            raise RuntimeError("Failed to generate image via Gemini.")

    elif openai_key:
        print("[BoomerShot] Using OpenAI API...")
        from openai import OpenAI

        client = OpenAI(api_key=openai_key)

        prompt = (
            "Transform this screenshot into a photo taken on a cheap, low-quality "
            "smartphone camera pointed at a computer screen. Make it blurry, with "
            "visible RGB subpixels, moiré patterns, screen glare from the camera "
            "flash in the center, reflection of a messy room on the monitor glass, "
            "and make it slightly tilted and off-center."
        )

        try:
            print("[BoomerShot] Trying OpenAI gpt-image-2 native image-to-image edit...")
            response = client.images.edit(
                model="gpt-image-2",
                image=open(input_image_path, "rb"),
                prompt=prompt,
            )
            image_url = response.data[0].url
            dl_response = requests.get(image_url)
            if dl_response.status_code == 200:
                new_image_bytes = dl_response.content
        except Exception as e:
            print(
                "[BoomerShot] gpt-image-2 edit failed, "
                f"falling back to gpt-4o vision + dall-e-3: {e}"
            )
            base64_image = base64.b64encode(image_bytes).decode("utf-8")

            # Step 1: Use gpt-4o vision to describe the screenshot
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Describe the contents of this screenshot in extreme detail, "
                                    "including UI text, controls, window placement, colors, and "
                                    "layout, so that it can be completely recreated. Keep it "
                                    "descriptive."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                            },
                        ],
                    }
                ],
            )
            description = response.choices[0].message.content

            # Step 2: Use DALL-E 3 to generate the boomer photo
            boomer_prompt = (
                "A photo taken on a cheap, low-quality smartphone camera pointed at "
                f"a computer screen. The screen displays: {description}. The photo "
                "is blurry, has visible RGB subpixels, moiré patterns, screen glare "
                "from the camera flash in the center, reflection of a messy room on "
                "the monitor glass, and is slightly tilted and off-center. It looks "
                "like a low-effort picture of a computer screen taken by an elderly person."
            )

            img_response = client.images.generate(
                model="dall-e-3",
                prompt=boomer_prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            image_url = img_response.data[0].url

            # Download the generated image
            dl_response = requests.get(image_url)
            if dl_response.status_code == 200:
                new_image_bytes = dl_response.content
            else:
                raise RuntimeError(f"Failed to download image from OpenAI: {dl_response.text}")

    if not new_image_bytes:
        raise RuntimeError("Failed to generate image via OpenAI.")

    # Write to a temporary file
    fd, temp_out_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    with open(temp_out_path, "wb") as f:
        f.write(new_image_bytes)

    return temp_out_path
