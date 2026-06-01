#!/bin/bash
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

add_to_bashrc() {
  local line="$1"
  grep -qF "$line" ~/.bashrc || echo "$line" >> ~/.bashrc
}

add_to_bashrc "bash $SCRIPTS_DIR/welcome.sh"
