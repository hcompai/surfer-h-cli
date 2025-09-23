import base64
import io
import re

import openai
from PIL import Image

from surfer_h_cli.utils import smart_resize

LOCALIZATION_PROMPT: str = """You are a precise UI element localization assistant. Your task is to find the exact click coordinates for a specific element in the screenshot.

INSTRUCTIONS:
1. Look at the provided screenshot carefully
2. Find the element described below: {component}
3. Determine the exact pixel coordinates for clicking on that element
4. The coordinates should be from the top-left corner (0,0) of the image
5. X = pixels from left edge, Y = pixels from top edge

OUTPUT FORMAT (REQUIRED):
You MUST respond with ONLY the coordinates in this exact format:
Click(X, Y)

Where X and Y are integer pixel values.

EXAMPLES:
- If the element is at position 150 pixels from left, 200 pixels from top: Click(150, 200)
- If the element is at position 50 pixels from left, 75 pixels from top: Click(50, 75)

Do NOT include any other text, explanations, or descriptions. ONLY output: Click(X, Y)

ELEMENT TO FIND: {component}"""


def localization_request(image: Image.Image, element_name: str, model: str, temperature: float = 0.0) -> dict:
    """Creates a localization prompt to send to an openai-compatible LLM."""

    # create prompt text
    localization_prompt = LOCALIZATION_PROMPT.format(component=element_name)

    # convert image to JPEG saved as base64
    width, height = image.size
    new_height, new_width = smart_resize(
        height,
        width,
        factor=14 * 2,  # patch size * patch merge
        min_pixels=4 * 28 * 28,  # n_token * patch size * patch size
        max_pixels=1280 * 28 * 28,  # n_pixel * patch size * patch size
    )
    image = image.resize((new_width, new_height), resample=Image.Resampling.LANCZOS).convert("RGB")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="JPEG", quality=90)
    image_base64 = base64.b64encode(image_bytes.getvalue()).decode("utf-8")
    # create openai request
    openai_request = {
        "messages": [
            {
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"detail": "auto", "url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                    {"type": "text", "text": localization_prompt},
                ],
                "role": "user",
            },
        ],
        "model": model,
        "temperature": temperature,
    }
    return openai_request


def parse_localization_response(completion, image: Image.Image):
    """Parses the localization response from the LLM and returns the x, y coordinates."""
    width, height = image.size
    if width > 1.0 and height > 1.0:
        new_height, new_width = smart_resize(
            height,
            width,
            factor=14 * 2,  # patch size * patch merge
            min_pixels=4 * 28 * 28,  # n_token * patch size * patch size
            max_pixels=1280 * 28 * 28,  # n_pixel * patch size * patch size
        )
    else:
        width, height, new_width, new_height = 1, 1, 1, 1

    response = completion.choices[0].message.content
    
    # Try to match Click(X, Y) format first (most likely with improved prompt)
    match = re.search(r"Click\((\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)\)", response)
    if match is None:
        # Try alternative regex patterns as fallback
        alternative_patterns = [
            r".*?(?<!\d)(\d+(?:\.\d+)?)(?!\d).*?(?<!\d)(\d+(?:\.\d+)?)(?!\d)",  # Original pattern
            r"\((\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)\)",      # (123, 456)
            r"x:\s*(\d+(?:\.\d+)?).*?y:\s*(\d+(?:\.\d+)?)", # x: 123, y: 456
            r"<(\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)>",        # <123, 456>
            r"(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)",       # 123, 456
            r"Point\((\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)\)", # Point(123, 456)
            r"coordinates?:\s*(\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)", # coordinate: 123, 456
        ]
        
        for pattern in alternative_patterns:
            alt_match = re.search(pattern, response, re.IGNORECASE)
            if alt_match:
                match = alt_match
                break
        
        if match is None:
            raise ValueError(f"Coordinates not found in completion content. Response was: {repr(response[:500])}")
    
    x = float(match.group(1))
    y = float(match.group(2))
    
    normalized_x, normalized_y = x / new_width, y / new_height
    
    if normalized_x > 1.0 or normalized_y > 1.0 or normalized_x < 0.0 or normalized_y < 0.0:
        # put the click in the image
        normalized_x, normalized_y = 0.25, 0.25
    
    resized_x, resized_y = int(normalized_x * width), int(normalized_y * height)
    return (resized_x, resized_y)


def localize_element(
    image: Image.Image, element_name: str, openai_client: openai.OpenAI, model: str, temperature: float = 0.0
) -> tuple[float, float]:
    prompt = localization_request(image=image, element_name=element_name, model=model, temperature=temperature)
    response = openai_client.chat.completions.create(**prompt)
    return parse_localization_response(response, image)