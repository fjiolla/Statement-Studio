#!/usr/bin/env bash
# Assemble the Hugging Face Space bundle in ./bundle:
#   backend/app + backend/samples + this folder's app.py, requirements.txt, packages.txt
# Upload it with:  hf upload fjiolla/statement-studio ./bundle . --repo-type=space
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
out="$here/bundle"
rm -rf "$out" && mkdir -p "$out"
cp -r "$root/backend/app" "$root/backend/samples" "$out/"
cp "$here/app.py" "$here/requirements.txt" "$here/packages.txt" "$out/"
find "$out" -name "__pycache__" -prune -exec rm -rf {} +
find "$out" -name ".DS_Store" -delete
echo "Bundle ready: $out ($(du -sh "$out" | cut -f1))"
