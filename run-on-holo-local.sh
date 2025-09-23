#!/bin/bash
set -euxo pipefail
uv sync

# Task related commands
TASK="On Google flights. Find a one-way business class flight from Buenos Aires to Amsterdam on the 10th of next month, and provide the details of the flight with the shortest duration."
URL="https://www.google.com/travel/flights"

# Parameters for the vLLM servers, you can also use the same server twice with the same model!

# Navigator
MODEL_NAV="Hcompany/Holo1-7B"
PORT_NAV="8083"
# you can locally launch the model with the following command in another terminal:
# CUDA_VISIBLE_DEVICES=0 vllm serve "$MODEL_NAV" --port "$PORT_NAV"

# Localizer
MODEL_LOC="Hcompany/Holo1-3B"
PORT_LOC="8084"
# you can locally launch the model with the following command in another terminal:
# CUDA_VISIBLE_DEVICES=1 vllm serve "$MODEL_LOC" --port "$PORT_LOC"

# Launch agent
uv run surfer-h-cli \
    --task "$TASK" \
    --url "$URL" \
    --max_n_steps 30 \
    --base_url_localization http://localhost:$PORT_LOC/v1 \
    --model_name_localization $MODEL_LOC \
    --base_url_navigation http://localhost:$PORT_NAV/v1 \
    --model_name_navigation $MODEL_NAV \
    --temperature_localization 0.7 \
    --headless-browser \

# When you are done, you can kill the vLLM servers
# bash src/open_surferh/holo1/kill_holo_vllm.sh --port $PORT_LOC
# bash src/open_surferh/holo1/kill_holo_vllm.sh --port $PORT_NAV
