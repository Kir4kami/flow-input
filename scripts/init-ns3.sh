#!/usr/bin/env bash
set -euo pipefail
cd /workspace
./ns3 configure --enable-examples --disable-tests --disable-python-bindings \
  --enable-modules='applications;internet;point-to-point;traffic-control' \
  --build-profile=optimized --disable-werror --disable-warnings \
  --disable-precompiled-headers
./ns3 build sim -j "${NS3_BUILD_JOBS:-2}"
