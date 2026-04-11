#!/bin/bash
# Build script for Render deployment
# Set this as Render's "Build Command":
#   pip install -r requirements.txt && bash build.sh

set -e

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Installing Node.js dependencies..."
cd frontend
npm ci --prefer-offline

echo "==> Building Next.js frontend..."
npm run build

cd ..
echo "==> Build complete. frontend/build/ is ready."
