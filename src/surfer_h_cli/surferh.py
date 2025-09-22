import argparse
import copy
import os
import threading
import time
from typing import Callable, Literal

from openai import OpenAI
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from surfer_h_cli.simple_browser import SimpleWebBrowserTools
from surfer_h_cli.skills.navigation_step import navigation_step
from surfer_h_cli.skills.validation import validate_web_voyager_answer
from surfer_h_cli.utils import image_to_b64

MESSAGE_TEMPLATES = {
    "thought": "🧠  Thought : {message}",
    "screenshot": "📷  Screenshot : {message}",
    "notes": "✍️  Notes : {message}",
    "action": "🛠️  Action : {message}",
    "answer": "💬  Answer : {message}",
    "announcement": "🎉  Announcement : {message}",
}
MESSAGE_COLORS = {
    "thought": "\033[35m",  # Magenta
    "screenshot": "\033[36m",  # Cyan
    "notes": "\033[33m",  # Yellow
    "action": "\033[32m",  # Green
    "answer": "\033[34m",  # Blue
    "announcement": "\033[37m",  # White
}


class AgentState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    task: str
    trajectory_id: str | None = None
    timestep: int
    url: str
    note_screenshots: list[str] = Field(default_factory=list)
    screenshots: list[Image.Image] = Field(default_factory=list)
    notes: str = ""
    navigation_actions: list[dict] = Field(default_factory=list)
    answer: str | None = None
    is_last_step: bool = False
    current_step: str = ""


_event_callback: Callable | None = None
_thread_local = threading.local()


def set_event_callback(callback: Callable):
    """Set the global event callback function"""
    global _event_callback
    _event_callback = callback


def get_current_state() -> AgentState | None:
    """Get the current agent state thread-safely"""
    return getattr(_thread_local, "current_agent_state", None)


def set_current_state(state: AgentState):
    """Set the current agent state thread-safely"""
    _thread_local.current_agent_state = state


def write_message(
    message: str | Image.Image, type: Literal["thought", "screenshot", "notes", "action", "answer", "announcement"]
):
    if isinstance(message, Image.Image):
        message = f"Image({message.width}x{message.height}, mode={message.mode})"
    # Nice formatting for all types of messages with emojis
    message = MESSAGE_TEMPLATES[type].format(message=message)
    print(f"{MESSAGE_COLORS[type]}{message}\033[0m")

    if _event_callback:
        _event_callback(type, str(message), get_current_state())


def execute_navigation_action(navigation_action: dict, browser: SimpleWebBrowserTools, refresh_url: str):
    action = navigation_action["action"]

    if action == "click_element":
        previous_tabs = browser.get_tabs()
        browser.click_at(navigation_action["x"], navigation_action["y"])
        new_tabs = browser.get_tabs()
        if len(new_tabs) > len(previous_tabs):
            browser.focus_tab(browser.find_newer_tab(previous_tabs, new_tabs).index)
    elif action == "write_element":
        browser.click_at(navigation_action["x"], navigation_action["y"])
        time.sleep(0.5)
        browser.write(navigation_action["content"], n_backspaces=100)
        time.sleep(0.5)
        browser.write("\n")
    elif action == "scroll":
        browser.scroll(navigation_action["direction"])
    elif action == "go_back":
        browser.goback()
    elif action == "refresh":
        browser.refresh()
    elif action == "wait":
        pass
    elif action == "restart":
        browser.goto(refresh_url)
    else:
        raise ValueError(f"Unknown action: {action}")

    # wait after any browser action
    time.sleep(2)


def update_state(current_state: AgentState, navigation_response: dict, browser: SimpleWebBrowserTools) -> AgentState:
    new_state = copy.deepcopy(current_state)
    new_state.timestep += 1
    new_state.navigation_actions.append(navigation_response)
    new_state.notes = new_state.notes + "\n" + navigation_response["notes"]
    new_state.screenshots.append(browser.screenshot())
    new_state.url = browser.get_tab_url()

    set_current_state(new_state)

    return new_state


def parse_args():
    """Parse CLI arguments."""
    # browser: SimpleWebBrowserTools,
    parser = argparse.ArgumentParser(description="OpenAI Multi-Client Configuration")
    parser.add_argument(
        "--task",
        type=str,
        default="Please find a recipe for avocado soup with a rating of 4.6 or higher and at least 100 reviews",
        help="Describe what the model should do",
    )
    parser.add_argument("--url", type=str, default="https://www.allrecipes.com", help="webside to start the task from")
    parser.add_argument("--max_n_steps", type=int, default=30, help="Maximum steps the agent can take")
    parser.add_argument("--max_time_seconds", type=int, default=600, help="Maximum time the task can take")
    parser.add_argument("--browser_width", type=int, default=1204, help="Width of the browser window")
    parser.add_argument("--browser_height", type=int, default=1204, help="Height of the browser window")
    # Navigation model
    parser.add_argument("--model_name_navigation", help="Override MODEL_NAME_NAVIGATION")
    parser.add_argument("--base_url_navigation", help="Override BASE_URL_NAVIGATION")
    parser.add_argument("--api-key-navigation", help="api key for navigation, overrides API_KEY_NAVIGATION")
    parser.add_argument("--temperature_navigation", type=float, default=0.7)
    parser.add_argument(
        "--n_navigation_screenshots", type=int, default=3, help="Maximum screenshots stored in the state"
    )
    # Localization model
    parser.add_argument("--api-key-localization", help="api key for navigation, overrides API_KEY_LOCALIZATION")
    parser.add_argument("--base_url_localization", help="Override BASE_URL_LOCALIZATION")
    parser.add_argument("--model_name_localization", help="Override MODEL_NAME_LOCALIZATION")
    parser.add_argument("--temperature_localization", type=float, default=0.0)

    # Validation
    parser.add_argument("--use_validator", action="store_true", help="Use a validator model.")
    parser.add_argument("--model_name_validation", help="Override MODEL_NAME_VALIDATION")
    parser.add_argument("--base_url_validation", help="Override BASE_URL_VALIDATION")
    parser.add_argument("--api-key-validation", help="api key for validation, overrides API_KEY_VALIDATION")
    parser.add_argument("--temperature_validation", type=float, default=0.0)

    parser.add_argument("--openai-api-key", help="API key for the OpenAI API")
    parser.add_argument("--headless-browser", action="store_true")
    parser.add_argument("--action-timeout", type=int, default=10)

    return parser.parse_args()


def create_openai_client(base_url: str | None, api_key: str) -> OpenAI:
    """Create and return an OpenAI client instance."""
    return OpenAI(base_url=base_url, api_key=api_key)


def get_env_or_cli(var_name: str, cli_value: str | None, default: str | None = None) -> str | None:
    """Retrieve value from CLI argument, fallback to environment variable, then to default."""
    if cli_value is not None:
        return cli_value
    return os.getenv(var_name, default)


def setup_client(name: str, base_url: str | None, openai_api_key: str | None, custom_api_key: str) -> OpenAI:
    """Set up the OpenAI client with proper key and base URL."""
    if base_url:
        api_key = custom_api_key
    else:
        print(f"defaulting to OpenAI API key for {name.upper()}")
        if openai_api_key is None:
            raise ValueError("OpenAI API key not set in either environment or through the CLI")
        api_key = openai_api_key
    print("Client", name, base_url, api_key[:4] + "..." if api_key else "No API Key")
    return create_openai_client(base_url, api_key)


def get_openai_model_names_and_clients(
    args,
) -> tuple[tuple[str, OpenAI], tuple[str, OpenAI], tuple[str, OpenAI] | tuple[None, None]]:
    # Handle navigation
    api_key_navigation = get_env_or_cli("API_KEY_NAVIGATION", args.api_key_navigation)
    openai_api_key = get_env_or_cli("OPENAI_API_KEY", args.openai_api_key)
    model_name_navigation = get_env_or_cli("MODEL_NAME_NAVIGATION", args.model_name_navigation, "gpt-4.1")
    base_url_navigation = get_env_or_cli("BASE_URL_NAVIGATION", args.base_url_navigation)

    assert model_name_navigation is not None
    print("Navigation Model Name:", model_name_navigation)
    assert base_url_navigation is not None
    print("Navigation Model URL:", base_url_navigation)

    openai_client_navigation = setup_client(
        name="navigation",
        base_url=base_url_navigation,
        openai_api_key=openai_api_key,
        custom_api_key=api_key_navigation or "EMPTY",
    )
    navigation_model_and_client = (model_name_navigation, openai_client_navigation)

    # Handle localization
    model_name_localization = get_env_or_cli("MODEL_NAME_LOCALIZATION", args.model_name_localization, "gpt-4.1")
    base_url_localization = get_env_or_cli("BASE_URL_LOCALIZATION", args.base_url_localization)
    api_key_localization = get_env_or_cli("API_KEY_LOCALIZATION", args.api_key_localization)

    assert model_name_localization is not None
    print("Localization Model Name:", model_name_localization)
    assert base_url_localization is not None
    print("Localization Model URL:", base_url_localization)

    openai_client_localization = setup_client(
        name="localization",
        base_url=base_url_localization,
        openai_api_key=openai_api_key,
        custom_api_key=api_key_localization or "EMPTY",
    )
    localization_model_and_client = (model_name_localization, openai_client_localization)

    # Handle validation
    validation_model_and_client: tuple[str, OpenAI] | tuple[None, None] = (None, None)
    if args.use_validator:
        model_name_validation = get_env_or_cli("MODEL_NAME_VALIDATION", args.model_name_validation, "gpt-4.1")
        base_url_validation = get_env_or_cli("BASE_URL_VALIDATION", args.base_url_validation, None)
        api_key_validation = get_env_or_cli("API_KEY_VALIDATION", args.api_key_validation)

        assert model_name_validation is not None
        print("Validation Model Name:", model_name_validation)
        # Note: base_url_validation can be None for OpenAI models (uses default endpoint)
        print("Validation Model URL:", base_url_validation or "default OpenAI endpoint")

        openai_client_validation = setup_client(
            name="validation",
            base_url=base_url_validation,
            openai_api_key=openai_api_key,
            custom_api_key=api_key_validation or "EMPTY",
        )
        validation_model_and_client = (model_name_validation, openai_client_validation)

    return (
        navigation_model_and_client,
        localization_model_and_client,
        validation_model_and_client,
    )


def validate_answer(
    current_state: AgentState,
    navigation_action: dict,
    n_navigation_screenshots: int,
    openai_client_validation: OpenAI | None,
    temperature_validation: float,
    model_name_validation: str | None,
    n_validation_retries: int = 2,
):
    screenshots_str = [
        image_to_b64(screenshot, "png") for screenshot in current_state.screenshots[-n_navigation_screenshots:]
    ]
    for i_retry in range(n_validation_retries):
        validator_response = validate_web_voyager_answer(
            task=current_state.task,
            answer=navigation_action["content"],
            screenshots=screenshots_str,
            is_answer=True,
            openai_client=openai_client_validation,
            openai_args={"temperature": temperature_validation, "model": model_name_validation},
        )
        # Validation tends to be not strict enough, so we retry or break on the first failure
        if not validator_response.success:
            break
        write_message(f"Validation {i_retry + 1}/{n_validation_retries} passed.", "announcement")
    return validator_response


def agent_loop(
    task: str,
    url: str,
    browser: SimpleWebBrowserTools,
    max_n_steps: int,
    max_time_seconds: int,
    n_navigation_screenshots: int,
    model_name_navigation: str,
    model_name_localization: str,
    model_name_validation: str | None,
    openai_client_navigation: OpenAI,
    openai_client_localization: OpenAI,
    openai_client_validation: OpenAI | None,
    temperature_navigation: float,
    temperature_localization: float,
    temperature_validation: float,
    use_validator: bool,
    trajectory_id: str | None = None,
):
    browser.goto(url)
    current_state = AgentState(
        task=task,
        trajectory_id=trajectory_id,
        timestep=0,
        url=url,
        screenshots=[browser.screenshot()],
    )

    start_time = time.time()

    while True:
        write_message(f"Step {current_state.timestep}", "announcement")
        write_message(current_state.screenshots[-1], "screenshot")

        force_answer = False
        if current_state.timestep == max_n_steps or time.time() - start_time > max_time_seconds:
            if current_state.timestep == max_n_steps:
                write_message(f"***** Max steps reached: {current_state.timestep} *****", "announcement")
            else:
                write_message(f"***** Max time reached: {time.time() - start_time}s *****", "announcement")
            force_answer = True

        navigation_response = navigation_step(
            task=current_state.task,
            previous_actions=", ".join([str(action) for action in current_state.navigation_actions]),
            step=current_state.current_step,
            notes=current_state.notes,
            force_answer=force_answer,
            screenshots=current_state.screenshots[-n_navigation_screenshots:],
            openai_client_navigation=openai_client_navigation,
            localization_openai_client=openai_client_localization,
            localizer_model_name=model_name_localization,
            navigator_model_name=model_name_navigation,
            temperature_navigation=temperature_navigation,
            temperature_localization=temperature_localization,
        )

        write_message(navigation_response["thought"], "thought")
        write_message(navigation_response["notes"], "notes")

        write_message(navigation_response["action"], "action")
        navigation_action = navigation_response["action"]

        if force_answer:
            write_message("***** Force answer *****", "announcement")
            write_message(navigation_action["content"], "answer")
            return navigation_action["content"], current_state.screenshots
        elif navigation_action["action"] == "answer":
            if use_validator:
                validator_response = validate_answer(
                    current_state,
                    navigation_action,
                    n_navigation_screenshots,
                    openai_client_validation,
                    temperature_validation,
                    model_name_validation,
                )
                if validator_response.success:
                    write_message("***** Validation passed *****", "announcement")
                    write_message(validator_response.why, "thought")
                    write_message(str(validator_response.answer), "answer")
                    return navigation_action["content"], current_state.screenshots
                else:
                    write_message(validator_response.why, "thought")
                    current_state.notes = f"{current_state.notes}\n"
            else:
                write_message("***** Return answer *****", "announcement")
                write_message(navigation_action["content"], "answer")
                return navigation_action["content"], current_state.screenshots
        else:
            execute_navigation_action(navigation_action, browser, url)

        new_state = update_state(current_state, navigation_response, browser)

        current_state = new_state


def main():
    cli_args = parse_args()
    browser = SimpleWebBrowserTools()
    browser.open_browser(
        headless=cli_args.headless_browser,
        width=cli_args.browser_width,
        height=cli_args.browser_height,
        action_timeout=cli_args.action_timeout,
    )

    (
        (model_name_navigation, openai_client_navigation),
        (model_name_localization, openai_client_localization),
        (model_name_validation, openai_client_validation),
    ) = get_openai_model_names_and_clients(cli_args)

    agent_loop(
        task=cli_args.task,
        url=cli_args.url,
        browser=browser,
        max_n_steps=cli_args.max_n_steps,
        max_time_seconds=cli_args.max_time_seconds,
        n_navigation_screenshots=cli_args.n_navigation_screenshots,
        model_name_localization=model_name_localization,
        model_name_navigation=model_name_navigation,
        model_name_validation=model_name_validation,
        openai_client_localization=openai_client_localization,
        openai_client_navigation=openai_client_navigation,
        openai_client_validation=openai_client_validation,
        temperature_navigation=cli_args.temperature_navigation,
        temperature_localization=cli_args.temperature_localization,
        temperature_validation=cli_args.temperature_validation,
        use_validator=cli_args.use_validator,
    )


if __name__ == "__main__":
    # agent_loop("What is the capital of France?", "https://www.bing.com", SimpleWebBrowserTools())

    # python forest.py
    # is equivalent to legacy:
    # agent_loop(
    #    "Please find a recipe for avocado soup with a rating of 4.6 or higher and at least 100 reviews",
    #    "https://www.allrecipes.com",
    #    SimpleWebBrowserTools(),
    # )
    main()
