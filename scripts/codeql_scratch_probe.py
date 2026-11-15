"""Scratch probe for the CodeQL pull request. Do not merge.

The first version passed sys.argv to subprocess.run(..., shell=True).
CodeQL models sys.argv as the commandargs threat model, and the default
code-scanning configuration does not enable that model, so that version
produced no alert. flask.request is a remote source, which the default
queries do track.
"""

import subprocess

from flask import request


def main() -> None:
    user_input = request.query_string
    subprocess.run(user_input, shell=True)


if __name__ == "__main__":
    main()
