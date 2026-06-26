import base64
import io
import os
import tempfile

import gi

try:
    gi.require_version("Secret", "1")
    from gi.repository import Secret

    HAS_SECRET = True
except Exception:
    HAS_SECRET = False

# Schema for keyring
KEYRING_SCHEMA = None
if HAS_SECRET:
    try:
        KEYRING_SCHEMA = Secret.Schema.new(
            "org.merklejerk.BoomerShot.ApiKeySchema",
            Secret.SchemaFlags.NONE,
            {
                "service": Secret.SchemaAttributeType.STRING,
                "key_type": Secret.SchemaAttributeType.STRING,
            },
        )
    except Exception as e:
        print(f"[BoomerShot] Failed to create Secret schema: {e}")


def is_keyring_locked():
    """Checks if the default GNOME Keyring collection is locked."""
    if not HAS_SECRET:
        return False
    try:
        service = Secret.Service.get_sync(Secret.ServiceFlags.NONE, None)
        if not service:
            return False
        col = Secret.Collection.for_alias_sync(
            service, "default", Secret.CollectionFlags.NONE, None
        )
        if col:
            return col.get_locked()
    except Exception as e:
        print(f"[BoomerShot] Failed to check if keyring is locked: {e}")
    return False


def get_api_key(key_type):
    """Retrieves the API key for key_type ('gemini' or 'openai').

    First checks GNOME Keyring (only if unlocked), then environment variables.
    """
    # 1. Try GNOME Keyring (only if not locked to avoid blocking/hanging)
    if HAS_SECRET and KEYRING_SCHEMA and not is_keyring_locked():
        try:
            attrs = {"service": "boomer-shot", "key_type": key_type}
            key = Secret.password_lookup_sync(KEYRING_SCHEMA, attrs, None)
            if key:
                return key
        except Exception as e:
            print(f"[BoomerShot] Keyring lookup failed: {e}")

    # 2. Try Environment Variables
    env_var_name = "GEMINI_API_KEY" if key_type == "gemini" else "OPENAI_API_KEY"
    return os.environ.get(env_var_name)


def save_api_key(key_type, value):
    """Saves the API key to GNOME Keyring."""
    if not HAS_SECRET or not KEYRING_SCHEMA:
        raise RuntimeError("GNOME Keyring (libsecret) is not available.")

    attrs = {"service": "boomer-shot", "key_type": key_type}
    label = f"BoomerShot {key_type.upper()} API Key"

    if value:
        success = Secret.password_store_sync(
            KEYRING_SCHEMA, attrs, Secret.COLLECTION_DEFAULT, label, value, None
        )
        if not success:
            raise RuntimeError("Failed to store key in GNOME Keyring.")
    else:
        # Clear the key if value is empty/None
        Secret.password_clear_sync(KEYRING_SCHEMA, attrs, None)


CONFIG_DIR = os.path.expanduser("~/.config/boomer-shot")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def get_preferred_provider():
    """Gets the preferred AI provider ('gemini' or 'openai')."""
    if os.path.exists(CONFIG_PATH):
        try:
            import json

            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                return data.get("provider", "gemini")
        except Exception as e:
            print(f"[BoomerShot] Failed to read config: {e}")
    return "gemini"


def save_preferred_provider(provider):
    """Saves the preferred AI provider ('gemini' or 'openai')."""
    try:
        import json

        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
        data["provider"] = provider
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[BoomerShot] Failed to save config: {e}")


def boomerfy_image(input_image_path):
    """Boomer-fies the screenshot using either Gemini (native image-to-image via gpt-image-2/Imagen)

    or OpenAI (native image-to-image via gpt-image-2 with vision+DALL-E 3 fallback).
    """
    import requests
    from PIL import Image

    gemini_key = get_api_key("gemini")
    openai_key = get_api_key("openai")

    if not gemini_key and not openai_key:
        raise ValueError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is configured.")

    # Determine which provider to use
    provider = get_preferred_provider()

    # Fallback logic if the preferred provider doesn't have a key configured
    if provider == "gemini" and not gemini_key:
        provider = "openai"
    elif provider == "openai" and not openai_key:
        provider = "gemini"

    # Read the input image bytes
    with open(input_image_path, "rb") as f:
        image_bytes = f.read()

    new_image_bytes = None

    if provider == "gemini":
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
