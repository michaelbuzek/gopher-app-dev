#!/usr/bin/env bash
# 🐹 Gopher Minigolf App Build Script for Render

set -o errexit  # Exit on any error

echo "🐹 Gopher App Build Starting..."

# Install Python dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Run database migrations
echo "🗄️ Running database migrations..."
flask db upgrade

echo "✅ Gopher App Build Complete!"
