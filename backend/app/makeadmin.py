"""Create an admin account, or make an existing account admin. Admins can delete any
proposal or comment.

    python -m app.makeadmin <username>

Prompts for the password (twice) and stores only its hash. Running it again for the
same username sets a new password.
"""

import getpass
import sys

from . import auth, db


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m app.makeadmin <username>")
    username = sys.argv[1]
    password = getpass.getpass(f"Password for {username}: ")
    if getpass.getpass("Repeat password: ") != password:
        sys.exit("Passwords don't match.")
    db.init_db()
    try:
        existed = auth.set_admin(username, password)
    except ValueError as e:
        sys.exit(str(e))
    print(f"{username} is {'now an admin, with the new password' if existed else 'created as an admin'}.")


if __name__ == "__main__":
    main()
