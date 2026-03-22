#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate
export DEV_INPUT_MODE=type
python3 -m src.main
