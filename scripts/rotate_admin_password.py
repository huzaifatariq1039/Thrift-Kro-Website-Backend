"""Interactively rotate an existing local administrator password."""

import argparse
from getpass import getpass

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import RoleEnum, User
from app.schemas.user import UserCreate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rotate an existing administrator password without logging it."
    )
    parser.add_argument("--email", required=True, help="Existing administrator email")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    password = getpass("New administrator password: ")
    confirmation = getpass("Confirm new administrator password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match; no database change was made.")

    # Reuse the application's password-strength validation without persisting this model.
    UserCreate(
        email=args.email,
        full_name="Administrator",
        password=password,
        role=RoleEnum.ADMIN,
    )

    db = SessionLocal()
    try:
        admin = (
            db.query(User)
            .filter(User.email == args.email, User.role == RoleEnum.ADMIN)
            .one_or_none()
        )
        if admin is None:
            raise SystemExit("No administrator with that email exists; no change was made.")

        admin.hashed_password = get_password_hash(password)
        admin.auth_provider = "local"
        db.commit()
        print("Administrator password rotated successfully.")
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
