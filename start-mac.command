#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  printf '%s\n' 'Complete the setup in README.md / Сначала настрой окружение по README.ru.md'
  exit 1
fi
exec .venv/bin/python app.py
