#!/bin/sh
set -eu

cat <<EOF >/usr/share/nginx/html/config.js
window.__REPOLENS_CONFIG__ = {
  apiBaseUrl: "${API_BASE_URL:-}"
};
EOF
