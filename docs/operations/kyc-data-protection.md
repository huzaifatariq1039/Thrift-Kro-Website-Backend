# KYC data protection launch gate

Seller identity verification is disabled by default because this repository
does not yet have an approved private-document storage and retention contract.
The API does not accept new verification payloads, does not return CNIC values
or document locations, and does not permit review decisions without safely
accessible evidence. Existing PostgreSQL rows are preserved to avoid deleting
locally managed pgAdmin data without an approved retention decision.

Before enabling KYC, the product owner, legal/privacy owner, and operations
owner must approve all of the following:

- legal basis, consent text and privacy-notice version;
- required fields and document types, with optional data removed;
- storage region, encryption/key ownership and rotation procedure;
- private object identifiers and short-lived, administrator-authorized access;
- role membership and periodic access review for KYC administrators;
- retention periods for pending, rejected, approved and abandoned requests;
- deletion/anonymization jobs, backup expiry and restore behavior;
- data-subject access/deletion handling and breach-response contacts.

Existing legacy rows must be inventoried and migrated or deleted under the
approved policy before collection is re-enabled. Do not copy identity values,
document references, signed URLs, or rejection narratives into logs or audit
event details. Administrative metadata reads are recorded in the append-only
audit trail using actor and request identifiers only.
