#!/usr/bin/env bash
set -e  # Exit immediately if any command fails

echo "==> Installing dependencies..."
pip install -r requirements.txt

echo "==> Running database migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Build complete!"
