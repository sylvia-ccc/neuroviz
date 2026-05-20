#!/bin/bash
cd "$(dirname "$0")"
source ../eeg102-receiver/venv/bin/activate 2>/dev/null || true
pip install fastapi uvicorn scipy numpy 2>/dev/null
python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8080 --reload
