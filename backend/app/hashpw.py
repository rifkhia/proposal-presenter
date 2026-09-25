"""Print a hash for EDIT_PASSWORD_HASH.

    python -m app.hashpw

Prompts for the password (twice) and prints the hash; the password itself is
never stored anywhere.
"""

import getpass
import sys

from .auth import hash_password


def main() -> None:
    password = getpass.getpass("Editor password: ")
    if len(password) < 8:
        sys.exit("Use at least 8 characters.")
    if getpass.getpass("Repeat password: ") != password:
        sys.exit("Passwords don't match.")
    print(hash_password(password))


if __name__ == "__main__":
    main()
