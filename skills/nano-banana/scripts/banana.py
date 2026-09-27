# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "google-genai",
#     "pillow",
#     "google-auth",
# ]
# ///
"""Generate or edit images with Nano Banana (Gemini image models).

Auth, first match wins:
  1. --api-key, or GEMINI_API_KEY / GOOGLE_API_KEY   -> Gemini API (key from aistudio.google.com/apikey)
  2. Application Default Credentials + a GCP project -> Vertex AI (gcloud auth application-default login)
Force one with --backend api|vertex.
"""

import argparse
import os
import sys

from google import genai
from google.genai import types
from google.genai.errors import APIError
from PIL import Image

MODEL_MAP = {
    "nano-banana": "gemini-2.5-flash-image",
    "nano-banana-pro": "gemini-3-pro-image",
    "nano-banana-2": "gemini-3.1-flash-image",
    "nano-banana-2-lite": "gemini-3.1-flash-lite-image",
    "nano-banana-lite": "gemini-3.1-flash-lite-image",
}
ASPECTS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]


def make_client(args):
    """Gemini API client when a key is available, else Vertex AI through ADC."""
    key = args.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if args.backend == "api" or (args.backend == "auto" and key):
        if not key:
            sys.exit("Error: --backend api needs GEMINI_API_KEY (or GOOGLE_API_KEY / --api-key). "
                     "Get a key at https://aistudio.google.com/apikey")
        return genai.Client(api_key=key), "gemini-api"

    import google.auth
    try:
        credentials, default_project = google.auth.default()
    except Exception:
        credentials, default_project = None, None
    project = (args.project or os.environ.get("GOOGLE_CLOUD_PROJECT")
               or os.environ.get("GCP_PROJECT") or default_project)
    location = args.location or os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    if not project:
        sys.exit("Error: no credentials. Set GEMINI_API_KEY (https://aistudio.google.com/apikey), "
                 "or run 'gcloud auth application-default login' and set GOOGLE_CLOUD_PROJECT / --project.")
    return genai.Client(vertexai=True, project=project, location=location, credentials=credentials), "vertex"


def main():
    parser = argparse.ArgumentParser(description="Generate or edit images using Nano Banana models.")
    parser.add_argument("-p", "--prompt", required=True, help="Text prompt describing the image")
    parser.add_argument("-f", "--filename", required=True, help="Output image filename")
    parser.add_argument("-i", "--input-image", action="append", default=[], help="Path to input/reference image(s) (up to 14)")
    parser.add_argument("-m", "--model", choices=sorted(MODEL_MAP), default="nano-banana-2-lite", help="Model selection (default: nano-banana-2-lite)")
    parser.add_argument("-r", "--resolution", choices=["1K", "2K", "4K"], default="1K", help="Output resolution (Gemini 3 image models)")
    parser.add_argument("-a", "--aspect-ratio", choices=ASPECTS, help="Output aspect ratio (default: model's choice)")
    parser.add_argument("--backend", choices=["auto", "api", "vertex"], default="auto", help="auto = API key if set, else Vertex AI")
    parser.add_argument("--api-key", help="Gemini API key (default: GEMINI_API_KEY / GOOGLE_API_KEY)")
    parser.add_argument("--project", help="GCP Project ID for Vertex AI")
    parser.add_argument("--location", default=None, help="GCP Location for Vertex AI (default: global)")

    args = parser.parse_args()

    if len(args.input_image) > 14:
        print("Error: Maximum of 14 input images allowed.", file=sys.stderr)
        sys.exit(1)

    model_id = MODEL_MAP[args.model]
    client, backend = make_client(args)

    print(f"Model: {model_id} ({backend})")
    print(f"Output: {args.filename}")
    print(f"Inputs: {args.input_image}")

    inputs = [Image.open(p) for p in args.input_image]
    contents = [args.prompt] + inputs if inputs else args.prompt

    image_config = {}
    if args.aspect_ratio:
        image_config["aspect_ratio"] = args.aspect_ratio
    if model_id != "gemini-2.5-flash-image":      # the original Nano Banana has one fixed size
        image_config["image_size"] = args.resolution
    config = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        image_config=types.ImageConfig(**image_config) if image_config else None,
    )

    try:
        response = client.models.generate_content(model=model_id, contents=contents, config=config)
        img_bytes = None
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                img_bytes = part.inline_data.data
                break
        if not img_bytes:
            raise ValueError("No image data found in response candidates.")
    except APIError as e:
        print(f"API Error generating image with {model_id}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error generating image with {model_id}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        os.makedirs(os.path.dirname(os.path.abspath(args.filename)), exist_ok=True)
        with open(args.filename, "wb") as f:
            f.write(img_bytes)
        print(f"Success! Image saved to {args.filename}")
    except Exception as e:
        print(f"Error saving image: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
