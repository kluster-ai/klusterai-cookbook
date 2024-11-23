#!/bin/bash

# Define base directory as the directory containing this script
BASE_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Navigate to script directory
cd "$BASE_DIR"

# Activate virtual environment
source "$BASE_DIR/.venv/bin/activate"

# Ensure dependencies are installed
pip install --quiet -r requirements.txt

# Run the script
python3 main.py >> klusterai_github_bot_report.log 2>&1

# Deactivate virtual environment
deactivate 