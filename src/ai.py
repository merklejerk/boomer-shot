import os
import tempfile
from typing import Optional

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
    "Transform this screenshot into a photo of a computer monitor taken by a cringey boomer on a "
    "smartphone camera, slightly off angle, complete with some glare/reflections. "
    "The screenshot contents (especially the text) and annotations should be preserved exactly"
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
    """Saves the custom image generation prompt to config.

    Sparse storage: Only saves 'prompt' if it differs from DEFAULT_PROMPT.
    """
    try:
        import copy
        import json

        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                try:
                    data = json.load(f)
                except Exception:
                    pass

        original_data = copy.deepcopy(data)

        if prompt == DEFAULT_PROMPT:
            if "prompt" in data:
                del data["prompt"]
        else:
            data["prompt"] = prompt

        if data != original_data:
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


def get_effective_provider() -> str:
    """Determines which provider ('gemini' or 'openai') will be used based on config and keys."""
    gemini_key = get_api_key("gemini")
    openai_key = get_api_key("openai")

    provider = get_preferred_provider()

    # Fallback logic if the preferred provider doesn't have a key configured
    if provider == "gemini" and not gemini_key and openai_key:
        return "openai"
    elif provider == "openai" and not openai_key and gemini_key:
        return "gemini"

    return provider


def save_preferred_provider(provider: str) -> None:
    """Saves the preferred AI provider ('gemini' or 'openai').

    Sparse storage: Only saves 'provider' if it differs from the default ('gemini').
    """
    try:
        import copy
        import json

        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                try:
                    data = json.load(f)
                except Exception:
                    pass

        original_data = copy.deepcopy(data)

        if provider == "gemini":
            if "provider" in data:
                del data["provider"]
        else:
            data["provider"] = provider

        if data != original_data:
            with open(CONFIG_PATH, "w") as f:
                json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[BoomerShot] Failed to save config: {e}")


def log_error(err_msg: str, tb_str: str = "") -> None:
    """Logs the error and optional traceback to ~/.config/boomer-shot/last_error.log."""
    import sys

    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        log_path = os.path.join(CONFIG_DIR, "last_error.log")
        with open(log_path, "w") as f:
            f.write(f"Error: {err_msg}\n")
            if tb_str:
                f.write("\nTraceback:\n")
                f.write(tb_str)
    except Exception as e:
        print(f"[BoomerShot] Failed to write error log: {e}", file=sys.stderr)


def encode_multipart_formdata(
    fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]
) -> tuple[bytes, str]:
    """Encodes fields and files into multipart/form-data bytes and boundary."""
    import uuid

    boundary = f"Boundary-{uuid.uuid4().hex}"
    body = []

    for name, value in fields.items():
        body.append(f"--{boundary}".encode("utf-8"))
        body.append(f'Content-Disposition: form-data; name="{name}"'.encode("utf-8"))
        body.append(b"")
        body.append(value.encode("utf-8"))

    for name, (filename, file_bytes, mime_type) in files.items():
        body.append(f"--{boundary}".encode("utf-8"))
        body.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode("utf-8")
        )
        body.append(f"Content-Type: {mime_type}".encode("utf-8"))
        body.append(b"")
        body.append(file_bytes)

    body.append(f"--{boundary}--".encode("utf-8"))
    body.append(b"")

    payload = b"\r\n".join(body)
    content_type = f"multipart/form-data; boundary={boundary}"
    return payload, content_type


def _boomerfy_via_gemini(api_key: str, image_bytes: bytes, prompt: str) -> bytes:
    """Boomer-fies the image using Gemini's REST API directly."""
    import base64
    import json
    import urllib.error
    import urllib.request

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={api_key}"

    # Base64 encode the input image
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "contents": [
            {
                "parts": [
                    {"inlineData": {"mimeType": "image/png", "data": image_b64}},
                    {"text": prompt},
                ]
            }
        ],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }

    headers = {"Content-Type": "application/json"}

    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )

    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        raise RuntimeError(
            f"Gemini API request failed: {e.code} {e.reason}\nResponse: {err_body}"
        ) from e

    try:
        parts = res_data["candidates"][0]["content"]["parts"]
        for part in parts:
            if "inlineData" in part:
                return base64.b64decode(part["inlineData"]["data"])
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected response structure from Gemini API: {res_data}") from e

    raise RuntimeError("Gemini API did not return any image data.")


def _boomerfy_via_openai(api_key: str, input_image_path: str, prompt: str) -> bytes:
    """Boomer-fies the image using OpenAI's REST API directly."""
    import json
    import urllib.error
    import urllib.request

    url = "https://api.openai.com/v1/images/edits"

    with open(input_image_path, "rb") as f:
        image_bytes = f.read()

    fields = {"prompt": prompt, "model": "gpt-image-2"}

    files = {"image": ("image.png", image_bytes, "image/png")}

    payload, content_type = encode_multipart_formdata(fields, files)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": content_type}

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        raise RuntimeError(
            f"OpenAI API request failed: {e.code} {e.reason}\nResponse: {err_body}"
        ) from e

    try:
        item = res_data["data"][0]
        if "b64_json" in item:
            import base64

            return base64.b64decode(item["b64_json"])
        elif "url" in item:
            image_url = item["url"]
            with urllib.request.urlopen(image_url) as response:
                return response.read()
        else:
            raise KeyError("Neither 'b64_json' nor 'url' found in response item")
    except (KeyError, IndexError) as e:
        keys_summary = list(res_data.keys()) if isinstance(res_data, dict) else "not a dict"
        raise RuntimeError(
            f"Unexpected response structure from OpenAI API (keys: {keys_summary})"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Failed to handle OpenAI image payload: {e}") from e


def boomerfy_image(input_image_path: str) -> str:
    """Boomer-fies the screenshot using either Gemini or OpenAI flagship models."""
    provider = get_effective_provider()

    gemini_key = get_api_key("gemini")
    openai_key = get_api_key("openai")

    if not gemini_key and not openai_key:
        raise ValueError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is configured.")

    # Read the input image bytes
    with open(input_image_path, "rb") as f:
        image_bytes = f.read()

    prompt = get_custom_prompt()
    new_image_bytes = None

    if provider == "gemini":
        print("[BoomerShot] Routing request to Gemini (gemini-2.5-flash-image)...")
        # Ensure we assert that key is present for the type system
        assert gemini_key is not None
        new_image_bytes = _boomerfy_via_gemini(gemini_key, image_bytes, prompt)

    elif provider == "openai":
        print("[BoomerShot] Routing request to OpenAI (gpt-image-2)...")
        # Ensure we assert that key is present for the type system
        assert openai_key is not None
        new_image_bytes = _boomerfy_via_openai(openai_key, input_image_path, prompt)

    if not new_image_bytes:
        raise RuntimeError(f"Failed to generate image via {provider.upper()}.")

    # Write to a temporary file
    fd, temp_out_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    with open(temp_out_path, "wb") as f:
        f.write(new_image_bytes)

    return temp_out_path
