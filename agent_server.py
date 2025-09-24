import base64
import json
import os
import threading
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # dotenv not available, environment variables should be set directly
    pass

from surfer_h_cli import surferh

app = FastAPI()


def get_model_config(model_name: str) -> tuple[str, str | None]:
    """
    Determine the appropriate API key and base URL based on the model name.
    Build full URL dynamically for HAI models.

    Returns:
        Tuple of (api_key, base_url)
    """
    # Convert model name to lowercase for comparison
    model_lower = model_name.lower()

    # Check if it's a GPT model
    if "gpt" in model_lower:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required for GPT models")
        return api_key, None  # Use default OpenAI base URL

    # Check if it's any Holo model (holo1, holo1-5, etc.)
    elif "holo" in model_lower:
        api_key = os.getenv("HAI_API_KEY")
        if not api_key:
            raise ValueError("HAI_API_KEY environment variable is required for Holo models")
        
        # Extract base URL from HAI_MODEL_URL
        hai_model_url = os.getenv("HAI_MODEL_URL", "")
        if not hai_model_url:
            raise ValueError("HAI_MODEL_URL environment variable is required for Holo models")
        # Split at '/models/' to get the base URL
        if "/models/" in hai_model_url:
            base_api_url = hai_model_url.split("/models/")[0]
        
        full_url = f"{base_api_url}/models/{model_name}"
        
        return api_key, full_url

    else:
        # Default to OpenAI for unknown models
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        return api_key, None


class StartAgentRequest(BaseModel):
    task: str = "On Google flights. Find a one-way business class flight from Buenos Aires to Amsterdam on the 10th of next month, and provide the details of the flight with the shortest duration."
    url: str = "https://www.google.com/travel/flights"
    max_n_steps: int = 30
    max_time_seconds: int = 600

    model_name_navigation: str = os.getenv("HAI_MODEL_NAME_NAVIGATION", "holo1-7b-20250521")
    temperature_navigation: float = 0.7
    n_navigation_screenshots: int = 3

    model_name_localization: str = os.getenv("HAI_MODEL_NAME_LOCALIZATION", "holo1-5-7b-20250915")
    temperature_localization: float = 0.7

    use_validator: bool = True
    model_name_validation: str = os.getenv("HAI_MODEL_NAME_VALIDATION", "holo1-7b-20250521")
    temperature_validation: float = 0.0

    headless_browser: bool = False
    action_timeout: int = 10


class TrajectoryInfo(BaseModel):
    trajectory_id: str
    task: str
    url: str
    status: str
    start_time: str
    end_time: str | None = None
    step_count: int = 0


class AgentRunner:
    def __init__(self):
        self.trajectories = {}
        self.running_agents = {}
        self.file_locks = {}
        self.trajectory_callbacks = {}
        self._global_callback_set = False

        trajectories_dir = Path("trajectories")
        trajectories_dir.mkdir(exist_ok=True)
        print(f"📁 Trajectories will be saved to: {trajectories_dir.absolute()}")

    def _global_event_callback(self, event_type, message, agent_state):
        """Global callback that routes events to the appropriate trajectory handler."""
        if agent_state and hasattr(agent_state, "trajectory_id") and agent_state.trajectory_id:
            # Route by trajectory_id for exact matching
            trajectory_id = agent_state.trajectory_id
            if trajectory_id in self.trajectory_callbacks:
                callback = self.trajectory_callbacks[trajectory_id]
                callback(event_type, message, agent_state)
                return
            else:
                print(f"⚠️  No callback found for trajectory {trajectory_id}")
        else:
            print(f"⚠️  Agent state missing trajectory_id, cannot route event {event_type}")
        print(f"⚠️  Could not route event {event_type} to appropriate trajectory")

    def start_agent(self, task: str, url: str, **kwargs):
        trajectory_id = str(uuid.uuid4())

        # Use defaults from StartAgentRequest model
        defaults = StartAgentRequest()

        max_n_steps = kwargs.get("max_n_steps", defaults.max_n_steps)
        max_time_seconds = kwargs.get("max_time_seconds", defaults.max_time_seconds)

        model_name_navigation = kwargs.get("model_name_navigation", defaults.model_name_navigation)
        temperature_navigation = kwargs.get("temperature_navigation", defaults.temperature_navigation)
        n_navigation_screenshots = kwargs.get("n_navigation_screenshots", defaults.n_navigation_screenshots)

        model_name_localization = kwargs.get("model_name_localization", defaults.model_name_localization)
        temperature_localization = kwargs.get("temperature_localization", defaults.temperature_localization)

        use_validator = kwargs.get("use_validator", defaults.use_validator)
        model_name_validation = kwargs.get("model_name_validation", defaults.model_name_validation)
        temperature_validation = kwargs.get("temperature_validation", defaults.temperature_validation)

        headless_browser = kwargs.get("headless_browser", defaults.headless_browser)
        action_timeout = kwargs.get("action_timeout", defaults.action_timeout)

        trajectory_data: dict[str, Any] = {
            "id": trajectory_id,
            "task": task,
            "url": url,
            "status": "running",
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "current_state": None,
            "step_count": 0,
            "events": [],
            "settings": {
                "max_n_steps": max_n_steps,
                "max_time_seconds": max_time_seconds,
                "model_name_navigation": model_name_navigation,
                "temperature_navigation": temperature_navigation,
                "n_navigation_screenshots": n_navigation_screenshots,
                "model_name_localization": model_name_localization,
                "temperature_localization": temperature_localization,
                "use_validator": use_validator,
                "model_name_validation": model_name_validation,
                "temperature_validation": temperature_validation,
                "headless_browser": headless_browser,
                "action_timeout": action_timeout,
            },
        }

        self.trajectories[trajectory_id] = trajectory_data
        self.file_locks[trajectory_id] = threading.Lock()

        self._initialize_trajectory_file(trajectory_id, trajectory_data)

        def trajectory_callback(event_type, message, agent_state):
            self._handle_agent_event(trajectory_id, event_type, message, agent_state)

        # Register the trajectory callback
        self.trajectory_callbacks[trajectory_id] = trajectory_callback

        # Set the global callback once if not already set
        if not self._global_callback_set:
            surferh.set_event_callback(self._global_event_callback)
            self._global_callback_set = True

        agent_thread = threading.Thread(
            target=self._run_agent, args=(trajectory_id, task, url, trajectory_callback), kwargs=kwargs
        )
        agent_thread.daemon = True
        agent_thread.start()

        self.running_agents[trajectory_id] = agent_thread

        return {
            "status": "started",
            "trajectory_id": trajectory_id,
            "task": task,
            "url": url,
            "settings": {
                "max_n_steps": max_n_steps,
                "max_time_seconds": max_time_seconds,
                "model_name_localization": model_name_localization,
                "use_validator": use_validator,
                "model_name_validation": model_name_validation,
                "headless_browser": headless_browser,
                "action_timeout": action_timeout,
            },
        }

    def _initialize_trajectory_file(self, trajectory_id: str, trajectory_data: dict[str, Any]):
        trajectories_dir = Path("trajectories")
        trajectories_dir.mkdir(exist_ok=True)

        file_path = trajectories_dir / f"trajectory_{trajectory_id}.json"

        file_data = {
            "id": trajectory_id,
            "task": trajectory_data["task"],
            "url": trajectory_data["url"],
            "status": trajectory_data["status"],
            "start_time": trajectory_data["start_time"],
            "end_time": None,
            "step_count": 0,
            "settings": trajectory_data["settings"],
            "events": [],
        }

        with open(file_path, "w") as f:
            json.dump(file_data, f, indent=2)

    def _run_agent(self, trajectory_id: str, task: str, url: str, callback, **kwargs):
        try:
            # Note: Global callback is now set in start_agent method

            # Use defaults from StartAgentRequest model
            defaults = StartAgentRequest()

            max_n_steps = kwargs.get("max_n_steps", defaults.max_n_steps)
            max_time_seconds = kwargs.get("max_time_seconds", defaults.max_time_seconds)

            model_name_navigation = kwargs.get("model_name_navigation", defaults.model_name_navigation)
            temperature_navigation = kwargs.get("temperature_navigation", defaults.temperature_navigation)
            n_navigation_screenshots = kwargs.get("n_navigation_screenshots", defaults.n_navigation_screenshots)

            model_name_localization = kwargs.get("model_name_localization", defaults.model_name_localization)
            temperature_localization = kwargs.get("temperature_localization", defaults.temperature_localization)

            use_validator = kwargs.get("use_validator", defaults.use_validator)
            model_name_validation = kwargs.get("model_name_validation", defaults.model_name_validation)
            temperature_validation = kwargs.get("temperature_validation", defaults.temperature_validation)

            headless_browser = kwargs.get("headless_browser", defaults.headless_browser)
            action_timeout = kwargs.get("action_timeout", defaults.action_timeout)

            browser = surferh.SimpleWebBrowserTools()
            browser.open_browser(headless=headless_browser, width=1920, height=1080, action_timeout=action_timeout)

            from openai import OpenAI

            # Get API configuration for navigation model
            try:
                nav_api_key, nav_base_url = get_model_config(model_name_navigation)
                openai_client_navigation = OpenAI(api_key=nav_api_key, base_url=nav_base_url)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Navigation model configuration error: {e}")

            # Get API configuration for localization model
            try:
                loc_api_key, loc_base_url = get_model_config(model_name_localization)
                openai_client_localization = OpenAI(api_key=loc_api_key, base_url=loc_base_url)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Localization model configuration error: {e}")

            # Get API configuration for validation model
            if use_validator:
                try:
                    val_api_key, val_base_url = get_model_config(model_name_validation)
                    openai_client_validation = OpenAI(api_key=val_api_key, base_url=val_base_url)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"Validation model configuration error: {e}")
            else:
                openai_client_validation = openai_client_navigation

            # Model names are now specific (e.g., "holo1-5-7b-20250915")
            # No replacement needed since frontend sends exact model names

            result = surferh.agent_loop(
                task=task,
                url=url,
                browser=browser,
                max_n_steps=max_n_steps,
                max_time_seconds=max_time_seconds,
                n_navigation_screenshots=n_navigation_screenshots,
                model_name_navigation=model_name_navigation,
                model_name_localization=model_name_localization,
                model_name_validation=model_name_validation,
                openai_client_navigation=openai_client_navigation,
                openai_client_localization=openai_client_localization,
                openai_client_validation=openai_client_validation,
                temperature_navigation=temperature_navigation,
                temperature_localization=temperature_localization,
                temperature_validation=temperature_validation,
                use_validator=use_validator,
                trajectory_id=trajectory_id,
            )

            # Extract message and images from the result
            if isinstance(result, tuple):
                completion_message = result[0]
                completion_images = result[1] if len(result) > 1 else []
            else:
                completion_message = str(result)
                completion_images = []

            self._complete_trajectory(trajectory_id, "completed", f"{completion_message}", completion_images)

        except Exception as e:
            self._complete_trajectory(trajectory_id, "error", f"Agent failed: {e}", None)
        finally:
            if trajectory_id in self.running_agents:
                del self.running_agents[trajectory_id]
            # Clean up trajectory callback
            if trajectory_id in self.trajectory_callbacks:
                del self.trajectory_callbacks[trajectory_id]

    def _complete_trajectory(self, trajectory_id: str, status: str, message: str, images: list | None = None):
        if trajectory_id in self.trajectories:
            trajectory = self.trajectories[trajectory_id]
            trajectory["status"] = status
            trajectory["end_time"] = datetime.now().isoformat()

            # Create a mock agent state with completion images if provided
            mock_agent_state = None
            if images:

                class MockAgentState:
                    def __init__(self, images, trajectory):
                        self.screenshots = images
                        self.timestep = trajectory["step_count"]
                        self.url = ""
                        self.notes = ""
                        self.task = trajectory["task"]
                        self.trajectory_id = trajectory["id"]

                mock_agent_state = MockAgentState(images, trajectory)

            self._handle_agent_event(trajectory_id, status, message, mock_agent_state)

    def _handle_agent_event(self, trajectory_id: str, event_type: str, message: str, agent_state):
        if trajectory_id not in self.trajectories:
            return

        trajectory = self.trajectories[trajectory_id]

        screenshot_b64 = None
        if (
            agent_state
            and agent_state.screenshots
            and (event_type.lower() == "screenshot" or event_type.lower() == "completed")
        ):
            try:
                img = agent_state.screenshots[-1]
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                screenshot_b64 = base64.b64encode(buffer.getvalue()).decode()
            except Exception:
                pass

        event_data = {
            "trajectory_id": trajectory_id,
            "type": event_type,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "screenshot": screenshot_b64,
            "agent_state": {
                "timestep": agent_state.timestep if agent_state else trajectory["step_count"],
                "url": agent_state.url if agent_state else "",
                "notes": agent_state.notes if agent_state else "",
                "task": agent_state.task if agent_state else trajectory["task"],
            }
            if agent_state
            else {"task": trajectory["task"]},
        }

        trajectory["current_state"] = agent_state
        if agent_state:
            trajectory["step_count"] = agent_state.timestep
        trajectory["events"].append(event_data.copy())

        self._save_event(trajectory_id, event_data)

    def _save_event(self, trajectory_id: str, event_data):
        with self.file_locks[trajectory_id]:
            trajectories_dir = Path("trajectories")
            log_file = trajectories_dir / f"trajectory_{trajectory_id}.json"

            try:
                with open(log_file, "r") as f:
                    file_data = json.load(f)
            except FileNotFoundError:
                file_data = {
                    "id": trajectory_id,
                    "task": self.trajectories[trajectory_id]["task"],
                    "url": self.trajectories[trajectory_id]["url"],
                    "status": self.trajectories[trajectory_id]["status"],
                    "start_time": self.trajectories[trajectory_id]["start_time"],
                    "end_time": self.trajectories[trajectory_id].get("end_time"),
                    "step_count": self.trajectories[trajectory_id]["step_count"],
                    "settings": self.trajectories[trajectory_id]["settings"],
                    "events": [],
                }

            saved_event = event_data.copy()

            file_data["events"].append(saved_event)
            file_data["step_count"] = len(file_data["events"])
            file_data["status"] = self.trajectories[trajectory_id]["status"]

            if self.trajectories[trajectory_id]["status"] in ["completed", "failed"]:
                file_data["end_time"] = datetime.now().isoformat()
                self.trajectories[trajectory_id]["end_time"] = file_data["end_time"]

            with open(log_file, "w") as f:
                json.dump(file_data, f, indent=2)

    def get_trajectory_status(self, trajectory_id: str):
        # First check if trajectory is in memory (active/recent)
        if trajectory_id in self.trajectories:
            trajectory = self.trajectories[trajectory_id]
            return {
                "trajectory_id": trajectory_id,
                "task": trajectory["task"],
                "url": trajectory["url"],
                "status": trajectory["status"],
                "start_time": trajectory["start_time"],
                "end_time": trajectory["end_time"],
                "step_count": trajectory["step_count"],
                "running": trajectory_id in self.running_agents,
                "current_state": trajectory["current_state"].dict() if trajectory["current_state"] else None,
            }

        # If not in memory, check persisted files
        trajectories_dir = Path("trajectories")
        json_file = trajectories_dir / f"trajectory_{trajectory_id}.json"

        if json_file.exists():
            try:
                with open(json_file, "r") as f:
                    file_data = json.load(f)

                return {
                    "trajectory_id": file_data["id"],
                    "task": file_data["task"],
                    "url": file_data["url"],
                    "status": file_data["status"],
                    "start_time": file_data["start_time"],
                    "end_time": file_data.get("end_time"),
                    "step_count": file_data.get("step_count", len(file_data.get("events", []))),
                    "running": False,
                    "current_state": None,
                }
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error reading trajectory file {json_file}: {e}")
                return None

        return None

    def list_trajectories(self):
        all_trajectories = []

        for trajectory_id, data in self.trajectories.items():
            trajectory_info = TrajectoryInfo(
                trajectory_id=trajectory_id,
                task=data["task"],
                url=data["url"],
                status=data["status"],
                start_time=data["start_time"],
                end_time=data.get("end_time"),
                step_count=data["step_count"],
            )
            all_trajectories.append(trajectory_info)

        trajectories_dir = Path("trajectories")
        if trajectories_dir.exists():
            for json_file in trajectories_dir.glob("trajectory_*.json"):
                trajectory_id = json_file.stem.replace("trajectory_", "")

                if trajectory_id in self.trajectories:
                    continue

                try:
                    with open(json_file, "r") as f:
                        file_data = json.load(f)

                    trajectory_info = TrajectoryInfo(
                        trajectory_id=file_data["id"],
                        task=file_data["task"],
                        url=file_data["url"],
                        status=file_data["status"],
                        start_time=file_data["start_time"],
                        end_time=file_data.get("end_time"),
                        step_count=file_data.get("step_count", len(file_data.get("events", []))),
                    )
                    all_trajectories.append(trajectory_info)

                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Error reading trajectory file {json_file}: {e}")
                    continue

        return all_trajectories

    def get_trajectory_events(self, trajectory_id: str):
        trajectories_dir = Path("trajectories")
        json_file = trajectories_dir / f"trajectory_{trajectory_id}.json"

        if not json_file.exists():
            return None

        try:
            with open(json_file, "r") as f:
                file_data = json.load(f)
            return file_data
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error reading trajectory file {json_file}: {e}")
            return None


agent_runner = AgentRunner()


@app.post("/start")
async def start_agent(request: StartAgentRequest):
    try:
        result = agent_runner.start_agent(
            task=request.task,
            url=request.url,
            max_n_steps=request.max_n_steps,
            max_time_seconds=request.max_time_seconds,
            model_name_navigation=request.model_name_navigation,
            temperature_navigation=request.temperature_navigation,
            n_navigation_screenshots=request.n_navigation_screenshots,
            model_name_localization=request.model_name_localization,
            temperature_localization=request.temperature_localization,
            use_validator=request.use_validator,
            model_name_validation=request.model_name_validation,
            temperature_validation=request.temperature_validation,
            headless_browser=request.headless_browser,
            action_timeout=request.action_timeout,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/status/{trajectory_id}")
async def get_status(trajectory_id: str):
    status = agent_runner.get_trajectory_status(trajectory_id)
    if not status:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    return status


@app.get("/trajectories")
async def list_trajectories():
    trajectories = agent_runner.list_trajectories()
    return {"trajectories": [trajectory.dict() for trajectory in trajectories], "count": len(trajectories)}


@app.get("/trajectory/{trajectory_id}")
async def get_trajectory(trajectory_id: str):
    """Get detailed trajectory information"""
    status = agent_runner.get_trajectory_status(trajectory_id)
    if not status:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    return status


@app.get("/trajectory/{trajectory_id}/events")
async def get_trajectory_events(trajectory_id: str):
    """Get full trajectory data including all historical events"""
    trajectory_data = agent_runner.get_trajectory_events(trajectory_id)
    if not trajectory_data:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    return trajectory_data


@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "ok", "message": "Agent server is running", "port": 7999}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7999)
