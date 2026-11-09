#!/bin/sh
set -eu

python /app/prepare_vm.py
exec uvicorn main:app --host 0.0.0.0 --port 8000
