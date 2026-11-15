---
name: safe-rm
description: Use when proving that rm -rf of a temporary build directory is not flagged.
license: MIT
---

# Safe rm

clean.sh removes a build directory under /tmp. That target is not /, ~, a variable, or *.
