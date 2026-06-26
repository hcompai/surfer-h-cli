#!/bin/bash
set -euo pipefail

echo "🚀 Starting Surfer H - Holo Model Run"
echo "======================================"

# Load environment variables using Python helper
eval "$(uv run python load_env.py HAI_API_KEY HAI_MODEL_URL_NAVIGATION HAI_MODEL_NAME_NAVIGATION HAI_MODEL_URL_LOCALIZATION HAI_MODEL_NAME_LOCALIZATION)"
echo ""

# Task configuration
TASK="Explore H Company's website to discover their recent blog posts, click on the latest post and read to the bottom of the page. Summarize the interesting findings and explain why they're significant for the AI and automation industry."
URL="https://www.hcompany.ai"

echo "🎯 Starting task: $TASK"
echo "🌐 Target URL: $URL"
echo "🤖 Model: $HAI_MODEL_NAME_NAVIGATION"
echo "🤖 Model: $HAI_MODEL_NAME_LOCALIZATION"
echo ""

# Sync dependencies
echo "📦 Syncing dependencies..."
uv sync

# Set up API keys for the run
export API_KEY_NAVIGATION="$HAI_API_KEY"
export API_KEY_LOCALIZATION="$HAI_API_KEY"

# Run the surfer-h-cli command
uv run surfer-h-cli \
    --task "$TASK" \
    --url "$URL" \
    --max_n_steps 30 \
    --base_url_localization "$HAI_MODEL_URL_LOCALIZATION" \
    --model_name_localization "$HAI_MODEL_NAME_LOCALIZATION" \
    --temperature_localization 0.7 \
    --base_url_navigation "$HAI_MODEL_URL_NAVIGATION" \
    --model_name_navigation "$HAI_MODEL_NAME_NAVIGATION" \
    --temperature_navigation 0.0