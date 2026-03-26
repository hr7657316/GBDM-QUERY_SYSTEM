#!/usr/bin/env bash
# Build script for Render.com deployment
# This runs during the build phase

set -e

echo "=== Installing backend dependencies ==="
cd backend
pip install -r requirements.txt

echo "=== Ingesting data into SQLite ==="
python3 ingest.py

echo "=== Installing frontend dependencies ==="
cd ../frontend
npm install

echo "=== Building frontend ==="
npm run build

echo "=== Build complete ==="
