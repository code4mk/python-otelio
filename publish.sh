#!/usr/bin/env bash
# Build and publish otelio to PyPI with uv.
# Usage: ./publish.sh            # build + upload to PyPI
#        ./publish.sh --test     # build + upload to TestPyPI
#
# Reads PYPI_API_TOKEN from .env (gitignored). On PyPI create a token at
# https://pypi.org/manage/account/token/ and put it in .env as:
#   PYPI_API_TOKEN=pypi-XXXX...
set -euo pipefail

cd "$(dirname "$0")"

# Load secrets (PYPI_API_TOKEN) from .env if present.
if [ -f .env ]; then
  set -o allexport
  source .env
  set +o allexport
fi

if [ -z "${PYPI_API_TOKEN:-}" ]; then
  echo "error: PYPI_API_TOKEN is not set (add it to .env or export it)." >&2
  exit 1
fi

# Clean previous artifacts and build fresh sdist + wheel into ./dist.
rm -rf dist build ./*.egg-info
uv build --out-dir dist .

if [[ "${1:-}" == "--test" ]]; then
  uv publish \
    --publish-url https://test.pypi.org/legacy/ \
    --username __token__ \
    --password "$PYPI_API_TOKEN" \
    dist/*
else
  uv publish \
    --username __token__ \
    --password "$PYPI_API_TOKEN" \
    dist/*
fi
