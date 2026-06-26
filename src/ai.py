import os
import tempfile
from typing import Any, Optional

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


def is_keyring_locked() -> bool:
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


def get_api_key(key_type: str) -> Optional[str]:
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


def save_api_key(key_type: str, value: Optional[str]) -> None:
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

DEFAULT_PROMPT = (
    "Transform this screenshot into a photo taken by a cringey boomer on a "
    "smartphone camera pointed at a computer screen."
)


def get_custom_prompt() -> str:
    """Gets the custom image generation prompt from config."""
    if os.path.exists(CONFIG_PATH):
        try:
            import json

            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                return data.get("prompt", DEFAULT_PROMPT)
        except Exception as e:
            print(f"[BoomerShot] Failed to read custom prompt: {e}")
    return DEFAULT_PROMPT


def save_custom_prompt(prompt: str) -> None:
    """Saves the custom image generation prompt to config."""
    try:
        import json

        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
        if data.get("prompt") == prompt:
            return
        data["prompt"] = prompt
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[BoomerShot] Failed to save custom prompt: {e}")


def get_preferred_provider() -> str:
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


def save_preferred_provider(provider: str) -> None:
    """Saves the preferred AI provider ('gemini' or 'openai')."""
    try:
        import json

        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
        if data.get("provider") == provider:
            return
        data["provider"] = provider
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[BoomerShot] Failed to save config: {e}")


def _boomerfy_via_gemini(client: Any, image_bytes: bytes, prompt: str) -> bytes:
    """Boomer-fies the image using Gemini's flagship image-to-image model."""
    from google.genai import types

    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type="image/png",
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[image_part, prompt],
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
        ),
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data:
            return part.inline_data.data

    raise RuntimeError("Gemini did not return any image data.")


def _boomerfy_via_openai(client: Any, input_image_path: str, prompt: str) -> bytes:
    """Boomer-fies the image using OpenAI's flagship gpt-image-2 editing API."""
    import requests

    response = client.images.edit(
        model="gpt-image-2",
        image=open(input_image_path, "rb"),
        prompt=prompt,
    )
    image_url = response.data[0].url
    dl_response = requests.get(image_url)
    if dl_response.status_code == 200:
        return dl_response.content
    raise RuntimeError(f"Failed to download image from OpenAI: {dl_response.text}")


def boomerfy_image(input_image_path: str) -> str:
    """Boomer-fies the screenshot using either Gemini or OpenAI flagship models."""
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

    prompt = get_custom_prompt()
    new_image_bytes = None

    if provider == "gemini":
        print("[BoomerShot] Routing request to Gemini (gemini-2.5-flash-image)...")
        from google import genai

        gemini_client: Any = genai.Client(api_key=gemini_key)
        new_image_bytes = _boomerfy_via_gemini(gemini_client, image_bytes, prompt)

    elif provider == "openai":
        print("[BoomerShot] Routing request to OpenAI (gpt-image-2)...")
        from openai import OpenAI

        openai_client: Any = OpenAI(api_key=openai_key)
        new_image_bytes = _boomerfy_via_openai(openai_client, input_image_path, prompt)

    if not new_image_bytes:
        raise RuntimeError(f"Failed to generate image via {provider.upper()}.")

    # Write to a temporary file
    fd, temp_out_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    with open(temp_out_path, "wb") as f:
        f.write(new_image_bytes)

    return temp_out_path
