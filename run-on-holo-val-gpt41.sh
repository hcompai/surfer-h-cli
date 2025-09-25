#!/bin/bash
set -euo pipefail

echo "🚀 Starting Surfer H - Holo1 Model Run with GPT-4o Validation"
echo "=============================================================="

# Load environment variables using Python helper
eval "$(uv run python3 load_env.py HAI_API_KEY HAI_MODEL_URL HAI_MODEL_NAME OPENAI_API_KEY)"
echo ""

# Sync dependencies
echo "📦 Syncing dependencies..."
uv sync

# Set up API keys for the run
export API_KEY_LOCALIZATION="$HAI_API_KEY"
export API_KEY_NAVIGATION="$HAI_API_KEY"

# Task configuration
TASK="Explore H Company's website to discover their recent blog posts, click on the latest post and read to the bottom of the page. Summarize the interesting findings and explain why they're significant for the AI and automation industry."
URL="https://www.hcompany.ai"

echo "🎯 Starting task: $TASK"
echo "🌐 Target URL: $URL"
echo "🤖 Model: $HAI_MODEL_NAME"
echo "🤖 Model URL: $HAI_MODEL_URL"
echo "✅ Validation: GPT-4.1 enabled"
echo ""

# Run the surfer-h-cli command
uv run surfer-h-cli \
    --task "$TASK" \
    --url "$URL" \
    --max_n_steps 30 \
    --base_url_localization "$HAI_MODEL_URL" \
    --model_name_localization "$HAI_MODEL_NAME" \
    --temperature_localization 0.0 \
    --base_url_navigation "$HAI_MODEL_URL" \
    --model_name_navigation "$HAI_MODEL_NAME" \
    --temperature_navigation 0.7 \
    --use_validator \
    --model_name_validation gpt-4.1-2025-04-14 \
    --temperature_validation 0.0 \
    "$@"