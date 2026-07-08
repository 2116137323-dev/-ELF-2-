#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WS_DIR="$(cd "${PKG_DIR}/../.." && pwd)"

if [ -f /opt/ros/humble/setup.bash ]; then
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash
fi
if [ -f "${WS_DIR}/install/setup.bash" ]; then
  # shellcheck disable=SC1091
  source "${WS_DIR}/install/setup.bash"
fi

if [ -z "${DISPLAY:-}" ]; then
  for candidate in :0 :1; do
    if xdpyinfo -display "${candidate}" >/dev/null 2>&1; then
      export DISPLAY="${candidate}"
      break
    fi
  done
fi

RVIZ_CONFIG="${PKG_DIR}/config/nav2_online_slam.rviz"
if [ ! -f "${RVIZ_CONFIG}" ]; then
  RVIZ_CONFIG="$(ros2 pkg prefix elf_slam)/share/elf_slam/config/nav2_online_slam.rviz"
fi

exec rviz2 -d "${RVIZ_CONFIG}"
