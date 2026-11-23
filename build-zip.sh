#!/usr/bin/env bash
# Build the plugin zip without VS Code, Docker or the Decky CLI.
# Result: out/Crosshair.zip, installable via Decky's developer mode ("Install Plugin from ZIP File").
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" != "--skip-frontend" ]]; then
    pnpm install --frozen-lockfile
    pnpm build
fi
[[ -f dist/index.js ]] || { echo "dist/index.js missing - frontend build failed?" >&2; exit 1; }

NAME="$(python3 -c 'import json; print(json.load(open("plugin.json"))["name"])')"
STAGE="out/$NAME"
rm -rf "$STAGE" "out/$NAME.zip"
mkdir -p "$STAGE/dist"

cp dist/index.js "$STAGE/dist/"
cp main.py plugin.json package.json LICENSE README.md "$STAGE/"

(cd out && python3 -m zipfile -c "$NAME.zip" "$NAME/")
rm -rf "$STAGE"
echo "Built out/$NAME.zip"
