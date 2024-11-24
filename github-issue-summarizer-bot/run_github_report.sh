#!/bin/bash

# Define base directory as the directory containing this script
BASE_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Default values
CONFIG_FILE="$BASE_DIR/config.yaml"
ENV_FILE=""
DEBUG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --env)
            ENV_FILE="$2"
            shift 2
            ;;
        --debug)
            DEBUG="--debug"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--config config.yaml] [--env .env] [--debug]"
            exit 1
            ;;
    esac
done

# Navigate to script directory
cd "$BASE_DIR"

# Activate virtual environment
source "$BASE_DIR/.venv/bin/activate"

# Ensure dependencies are installed
pip install --quiet -r requirements.txt

# Construct the command with arguments
CMD="python3 main.py --config \"$CONFIG_FILE\""
if [ -n "$ENV_FILE" ]; then
    CMD="$CMD --env \"$ENV_FILE\""
fi
if [ -n "$DEBUG" ]; then
    CMD="$CMD --debug"
fi

# Run the script
echo "Running with config: $CONFIG_FILE"
[ -n "$ENV_FILE" ] && echo "Using env file: $ENV_FILE"
[ -n "$DEBUG" ] && echo "Debug mode enabled"
eval "$CMD" >> klusterai_github_bot_report.log 2>&1

# Deactivate virtual environment
deactivate 