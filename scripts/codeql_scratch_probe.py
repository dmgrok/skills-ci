"""Scratch probe for the CodeQL pull request. Do not merge."""

import subprocess
import sys


def main() -> None:
    user_input = sys.argv[1]
    subprocess.run(user_input, shell=True)


if __name__ == "__main__":
    main()
