# Media Lifecycle and Privacy Policy

## Scope and authority

The `media_assets` table is the authority for every image uploaded through the application. A provider URL alone is never proof of ownership and cannot be attached to a product unless it resolves to a pending asset owned by the same seller.

Product media is public. Identity and KYC evidence is private. The active release does not accept KYC uploads: seller verification remains fail closed until private storage, signed administrator access, an approved retention period, and incident procedures are configured. A KYC asset can never use `PUBLIC` visibility because the database enforces that invariant.

## Product upload lifecycle

1. `POST /api/v1/upload/image` validates the authenticated verified seller, streams at most 5 MB, checks magic bytes and decoded dimensions, strips metadata through safe re-encoding, and applies the provider compression policy.
2. The provider public ID, owner, purpose, visibility, content type, byte size, dimensions, moderation state, and URL are stored as a `PENDING` asset.
3. The upload must be attached to a product within 24 hours. Product creation locks the asset and verifies owner, purpose, visibility, state, and expiry before changing it to `ATTACHED`.
4. Unknown URLs, another seller's URLs, expired uploads, and already attached assets are rejected.

Semantic image moderation is not automated in this release. The explicit `NOT_REVIEWED` moderation state records that fact instead of implying a scan occurred. Technical image validation is mandatory. If pre-publication semantic moderation becomes a launch requirement, product attachment must require `APPROVED` before the feature is advertised.

## Retention and deletion

- Unattached uploads expire after 24 hours.
- Replaced product images are eligible for deletion immediately after the replacement transaction commits.
- Soft-deleted products retain managed images for 30 days so the seller can restore the listing.
- Restoring a product cancels scheduled deletion until a cleanup worker acquires a deletion lease. A product whose managed images are being or have been destroyed cannot be restored.
- Provider deletion is idempotent. Database rows are retained as deletion evidence, while the stored URL is redacted after confirmed provider deletion.
- Media backfilled from pre-lifecycle product rows is marked `legacy`. The cleanup command does not claim provider deletion for those objects; operators must reconcile or delete them with verified provider identifiers.

Run the bounded cleanup worker from a scheduler at least hourly:

```powershell
python -m scripts.cleanup_media_assets --limit 100
```

The worker row-locks due assets and gives each one a 15-minute `DELETING` lease before calling the provider. This prevents restoration from racing with external deletion without holding a database transaction across the provider call. A worker crash can safely retry after the lease expires because provider deletion is idempotent. Provider failures return assets to `DELETION_PENDING` with a five-minute retry delay.

## Operational checks

- Alert on expired `PENDING` assets, old `DELETION_PENDING` assets, and expired `DELETING` leases.
- Compare Cloudinary inventory to active `cloudinary` media rows during cost reconciliation.
- Never log upload bytes, identity documents, signed URLs, provider secrets, or KYC fields.
- Back up lifecycle metadata with the application database; provider objects require their own recovery policy.
