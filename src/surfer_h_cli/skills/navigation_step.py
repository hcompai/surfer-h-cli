import json
from datetime import datetime
from typing import Literal

import openai
from PIL import Image

from surfer_h_cli.skills.localization import localize_element as localize_element_old
from surfer_h_cli.skills.localization_1_5 import localize_element_structured
from surfer_h_cli.skills.navigation_models import AbsWebAgentNavigate, NavigationState, WebAgentAnswer
from surfer_h_cli.utils import image_to_b64, smart_resize

NAVIGATION_PROMPT: str = f"""Imagine you are a robot browsing the web, just like humans. Now you need to complete a task.
In each iteration, you will receive an Observation that includes the last  screenshots of a web browser and the current memory of the agent.
You have also information about the step that the agent is trying to achieve to solve the task.
Carefully analyze the visual information to identify what to do, then follow the guidelines to choose the following action.
You should detail your thought (i.e. reasoning steps) before taking the action.
Also detail in the notes field of the action the extracted information relevant to solve the task.
Once you have enough information in the notes to answer the task, return an answer action with the detailed answer in the notes field.
This will be evaluated by an evaluator and should match all the criteria or requirements of the task.

Guidelines:
- store in the notes all the relevant information to solve the task that fulfill the task criteria. Be precise
- Use both the task and the step information to decide what to do
- if you want to write in a text field and the text field already has text, designate the text field by the text it contains and its type
- If there is a cookies notice, always accept all the cookies first
- The observation is the screenshot of the current page and the memory of the agent.
- If you see relevant information on the screenshot to answer the task, add it to the notes field of the action.
- If there is no relevant information on the screenshot to answer the task, add an empty string to the notes field of the action.
- If you see buttons that allow to navigate directly to relevant information, like jump to ... or go to ... , use them to navigate faster.
- In the answer action, give as many details a possible relevant to answering the task.
- if you want to write, don't click before. Directly use the write action
- to write, identify the web element which is type and the text it already contains
- If you want to use a search bar, directly write text in the search bar
- Don't scroll too much. Don't scroll if the number of scrolls is greater than 3
- Don't scroll if you are at the end of the webpage
- Only refresh if you identify a rate limit problem
- If you are looking for a single flights, click on round-trip to select 'one way'
- Never try to login, enter email or password. If there is a need to login, then go back.
- If you are facing a captcha on a website, try to solve it.

- if you have enough information in the screenshot and in the notes to answer the task, return an answer action with the detailed answer in the notes field
- The current date is {datetime.today().strftime("%A, %B %-d, %Y")}."""


def response_format_json_schema(json_schema: dict, name: str, description: str = "", strict: bool = True) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "schema": json_schema,
            "name": name,
            "description": description,
            "strict": strict,
        },
    }


def image_content(image: Image.Image, format: Literal["jpeg", "png"] = "jpeg") -> dict:
    image_base64 = image_to_b64(image, format)
    return {"type": "image_url", "image_url": {"detail": "auto", "url": f"data:image/{format};base64,{image_base64}"}}


def navigation_request(
    task: str,
    previous_actions: str,
    step: str,
    notes: str,
    force_answer: bool,
    screenshots: list[Image.Image],
    model: str,
    use_smart_resize: bool = True,
    image_format: Literal["jpeg", "png"] = "jpeg",
    temperature: float = 0.7,
) -> dict:
    messages = [
        {
            "role": "system",
            "content": json.dumps(
                {
                    "guidelines": NAVIGATION_PROMPT,
                    "state_format": NavigationState.model_json_schema(),
                    "answer_format": AbsWebAgentNavigate.get_only_properties_schema(),
                }
            ),
        },
    ]

    user_content = [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "task": task,
                    "previous_actions": previous_actions,
                    "step": step,
                    "notes": notes,
                },
                separators=(",", ":"),
            ),
        },
    ]

    if use_smart_resize:
        images = []
        for screenshot in screenshots:
            height, width = smart_resize(screenshot.height, screenshot.width)
            images.append(screenshot.resize((width, height), resample=Image.Resampling.LANCZOS).convert("RGB"))
    else:
        images = screenshots

    user_content.extend([image_content(image, format=image_format) for image in images])
    messages.append({"role": "user", "content": user_content})  # type: ignore

    if force_answer:
        response_format = WebAgentAnswer.get_json_schema()
    else:
        response_format = AbsWebAgentNavigate.get_json_schema()
    openai_request = {
        "messages": messages,
        "model": model,
        "temperature": temperature,
        "response_format": response_format,
    }
    return openai_request


def parse_navigation_response(response: openai.types.chat.ChatCompletion) -> dict:
    content = response.choices[0].message.content
    assert content is not None
    return json.loads(content)


def localize_element_by_model(
    image: Image.Image,
    element_name: str,
    openai_client: openai.OpenAI,
    model: str,
    temperature: float = 0.0,
) -> tuple[int, int]:
    """Localizes an element using the appropriate method based on the model."""
    if model.startswith("holo1-5"):
        # Use new structured method
        click_action = localize_element_structured(
            image=image,
            element_name=element_name,
            openai_client=openai_client,
            model=model,
            temperature=temperature,
        )
        return (click_action.x, click_action.y)
    else:
        # Use old method
        coords = localize_element_old(
            image=image,
            element_name=element_name,
            openai_client=openai_client,
            model=model,
            temperature=temperature,
        )
        return (int(coords[0]), int(coords[1]))


def navigation_step(
    task: str,
    previous_actions: str,
    step: str,
    notes: str,
    force_answer: bool,
    screenshots: list[Image.Image],
    openai_client_navigation: openai.OpenAI,
    localizer_model_name: str,
    navigator_model_name: str,
    localization_openai_client: openai.OpenAI,
    temperature_navigation: float = 0.7,
    temperature_localization: float = 0.0,
):
    openai_request = navigation_request(
        task=task,
        previous_actions=previous_actions,
        step=step,
        notes=notes,
        force_answer=force_answer,
        screenshots=screenshots,
        model=navigator_model_name,
        temperature=temperature_navigation,
    )
    response = openai_client_navigation.chat.completions.create(**openai_request)
    parsed_response = parse_navigation_response(response)

    action = parsed_response["action"]
    if action["action"] == "click_element":
        element = action["element"]
        x, y = localize_element_by_model(
            image=screenshots[-1],
            element_name=element,
            openai_client=localization_openai_client,
            model=localizer_model_name,
            temperature=temperature_localization,
        )
        action["x"] = x
        action["y"] = y

    elif action["action"] == "write_element":
        element = action["element"]
        x, y = localize_element_by_model(
            image=screenshots[-1],
            element_name=element,
            openai_client=localization_openai_client,
            model=localizer_model_name,
            temperature=temperature_localization,
        )
        action["x"] = x
        action["y"] = y

    return parsed_response
