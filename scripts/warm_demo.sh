#!/usr/bin/env bash
# Fetch the demo PRs and ask the model once, so the live demo is instant and works if the wifi is slow.
set -eu
export SURGEON_CACHE_DIR="${SURGEON_CACHE_DIR:-/tmp/surgeon-cache}"
SHA=3bc11384b38879091df0671fa4231c31cca9c58d
surgeon analyze pallets/flask#2936 -q
surgeon analyze cockpit-project/cockpit#19024 --at "$SHA" -q
surgeon split cockpit-project/cockpit#19024 --at "$SHA" --out "${TMPDIR:-/tmp}/surgeon-demo-patches" > /dev/null
echo "demo warmed in $SURGEON_CACHE_DIR"
