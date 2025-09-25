import base64
import io
from typing import Literal

import openai
from PIL import Image
from pydantic import BaseModel, Field


class ClickAbsoluteAction(BaseModel):
    """Click at absolute coordinates."""

    action: Literal["click_absolute"] = "click_absolute"
    x: int = Field(description="The x coordinate, number of pixels from the left edge.")
    y: int = Field(description="The y coordinate, number of pixels from the top edge.")


def create_localization_prompt(component: str) -> str:
    """Creates the localization prompt with JSON schema."""
    return f"""Localize an element on the GUI image according to the provided target and output a click position.
 * You must output a valid JSON following the format: {ClickAbsoluteAction.model_json_schema()}
 Your target is:

{component}"""


def resize_image_for_localization(image: Image.Image, target_size: tuple[int, int] = (1000, 500)) -> Image.Image:
    """Resize image for localization with simple resize instead of smart_resize."""
    return image.resize(target_size, resample=Image.Resampling.LANCZOS).convert("RGB")


def localization_request(image: Image.Image, element_name: str, model: str, temperature: float = 0.0) -> dict:
    """Creates a localization request with structured JSON output."""
    
    # Resize image using simple resize instead of smart_resize
    resized_image = resize_image_for_localization(image)
    
    # Create prompt text
    localization_prompt = create_localization_prompt(element_name)
    
    # Convert image to JPEG saved as base64
    image_bytes = io.BytesIO()
    resized_image.save(image_bytes, format="JPEG", quality=90)
    image_base64 = base64.b64encode(image_bytes.getvalue()).decode("utf-8")
    
    # Create openai request with structured output
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
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "click_absolute_action",
                "schema": ClickAbsoluteAction.model_json_schema(),
                "strict": True
            }
        },
    }
    return openai_request


def parse_localization_response(completion, original_image: Image.Image, resized_image: Image.Image) -> tuple[int, int]:
    """Parses the JSON localization response and scales coordinates back to original image size."""
    
    # Parse JSON response into ClickAbsoluteAction model
    response_content = completion.choices[0].message.content
    click_action = ClickAbsoluteAction.model_validate_json(response_content)
    
    # Get image dimensions
    original_width, original_height = original_image.size
    resized_width, resized_height = resized_image.size
    
    # Scale coordinates from resized image back to original image
    scale_x = original_width / resized_width
    scale_y = original_height / resized_height
    
    original_x = int(click_action.x * scale_x)
    original_y = int(click_action.y * scale_y)
    
    # Ensure coordinates are within bounds
    original_x = max(0, min(original_x, original_width - 1))
    original_y = max(0, min(original_y, original_height - 1))
    
    return (original_x, original_y)


def localize_element(
    image: Image.Image, element_name: str, openai_client: openai.OpenAI, model: str, temperature: float = 0.0
) -> tuple[int, int]:
    """Localizes an element and returns coordinates in the original image dimensions."""
    
    # Create resized image for processing
    resized_image = resize_image_for_localization(image)
    
    # Create the request
    request_data = localization_request(image=image, element_name=element_name, model=model, temperature=temperature)
    
    # Get response from OpenAI
    response = openai_client.chat.completions.create(**request_data)
    
    # Parse response and scale coordinates back to original image
    return parse_localization_response(response, original_image=image, resized_image=resized_image)


def localize_element_structured(
    image: Image.Image, element_name: str, openai_client: openai.OpenAI, model: str, temperature: float = 0.0
) -> ClickAbsoluteAction:
    """Localizes an element and returns the structured ClickAbsoluteAction with original image coordinates."""
    
    coordinates = localize_element(image, element_name, openai_client, model, temperature)
    
    return ClickAbsoluteAction(x=coordinates[0], y=coordinates[1])
