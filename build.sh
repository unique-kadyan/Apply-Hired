#!/bin/bash
set -e

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Node version: $(node --version)"
echo "==> npm version:  $(npm --version)"

echo "==> Installing Node.js dependencies..."
cd frontend
npm ci

echo "==> Building Next.js frontend..."
npm run build

cd ..
echo "==> Build complete. frontend/build/ is ready."
