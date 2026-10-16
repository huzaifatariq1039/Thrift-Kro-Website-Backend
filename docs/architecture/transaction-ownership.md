# Transaction and provider-call ownership

## Database writes

The public CRUD/service operation owns its database transaction unless its
docstring explicitly says that it only stages changes. An owning operation must
commit exactly once after all database invariants pass and roll back before it
maps or re-raises any failure. Routers must not add a second commit around an
owning operation.

Multi-step domain operations such as checkout, refunds, review creation, cart
mutation, and authentication lifecycle changes remain single transaction
boundaries. Internal helpers called by those operations stage data with
`flush()` when identifiers are needed; they do not commit independently.

External network calls must not occur while database row locks are held. Fetch
or upload provider data before opening a write transaction, or commit durable
state before dispatching an external side effect through a separately designed
outbox.

## Active provider calls

Active Google identity and Cloudinary upload calls have network-layer timeouts,
at most two attempts with a short bounded backoff, and a per-process circuit
breaker. Only transient connection, timeout, throttling, and server failures
consume retry and circuit budgets. Client/authentication failures are returned
without retrying and do not open the circuit.

When a circuit is open, the API returns a redacted `503` response with a
`Retry-After` header. Exhausted transient calls return a redacted provider
failure; provider response bodies and credentials never enter public errors or
logs.

## Deferred VTON provider

The VTON inference architecture is outside the current release scope. Its
existing adapter must not be treated as production-ready, and no retry or
circuit policy for a future engine is approved here. The selected engine must
receive its own idempotency, timeout, concurrency, and retry design when that
architecture is implemented.
