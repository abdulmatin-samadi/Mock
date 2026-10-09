#!/bin/sh
# Netlify build: write the proxy rule that sends every request without a static file to the backend.
# Files in public/ (the /static/ CSS, JS and images) are served by Netlify first.
set -e
BACKEND_URL="${BACKEND_URL%/}"
if [ -z "$BACKEND_URL" ]; then
  echo "BACKEND_URL is not set" >&2
  exit 1
fi
printf '/*  %s/:splat  200\n' "$BACKEND_URL" > public/_redirects
echo "Proxying to $BACKEND_URL"
cat public/_redirects
