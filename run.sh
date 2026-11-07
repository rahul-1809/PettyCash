#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "===================================================="
echo " Starting PettyCash Pro Fullstack Application"
echo "===================================================="

# If frontend dist doesn't exist, build it
if [ ! -d "frontend/dist" ]; then
    echo "Building React frontend..."
    cd frontend && npm run build && cd ..
fi

echo "Launching server on http://localhost:8000 ..."
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

