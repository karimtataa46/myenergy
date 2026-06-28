#!/usr/bin/env bash
# Start myEnergy locally. Run:  ./start.sh   then open http://localhost:8000
set -e
cd "$(dirname "$0")/backend"
exec python3 -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --loop asyncio --http h11
