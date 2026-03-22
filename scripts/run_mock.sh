#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate
export FAKE_TRANSCRIPT_TEXT="${FAKE_TRANSCRIPT_TEXT:-${MOCK_TRANSCRIPT_TEXT:-test command}}"
python3 -m src.main
