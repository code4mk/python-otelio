#!/usr/bin/env bash
# Build and publish otelio to PyPI.
# Usage: ./publish.sh            # build + upload to PyPI
#        ./publish.sh --test     # build + upload to TestPyPI
set -euo pipefail

cd "$(dirname "$0")"

rm -rf dist build ./*.egg-info

python -m build

if [[ "${1:-}" == "--test" ]]; then
    python -m twine upload --repository testpypi dist/*
else
    python -m twine upload dist/*
fi
