#!/bin/bash
# Double-click to install or update Network Focus on this Mac.
# Uses install.sh next to this file if there is one, otherwise the latest from GitHub.
cd "$(dirname "$0")" || exit 1
if [ -f ./install.sh ]; then
  bash ./install.sh "$@"
else
  curl -fsSL https://raw.githubusercontent.com/jasper-osita/network-focus-maven/main/install.sh | bash -s -- "$@"
fi
echo
read -n 1 -s -r -p "Press any key to close this window."
echo
