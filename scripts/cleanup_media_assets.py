"""Delete expired managed media after database lifecycle rules select it."""

import argparse

from app.core.database import SessionLocal
from app.services.media_lifecycle import cleanup_due_media_assets
from app.services.upload import delete_image_from_cloudinary


def _positive_limit(value: str) -> int:
    parsed = int(value)
    if parsed < 1 or parsed > 500:
        raise argparse.ArgumentTypeError("limit must be between 1 and 500")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=_positive_limit, default=100)
    args = parser.parse_args()

    with SessionLocal() as db:
        deleted = cleanup_due_media_assets(
            db,
            provider_delete=delete_image_from_cloudinary,
            limit=args.limit,
        )
    print(f"Deleted {deleted} managed media asset(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
