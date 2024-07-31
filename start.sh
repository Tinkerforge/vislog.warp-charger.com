#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
./venv/bin/gunicorn -w 1 --bind unix:app.sock main:app
