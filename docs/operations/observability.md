# Production observability and audit operations

## Request correlation and privacy

Every HTTP response includes `X-Request-ID`. A valid inbound UUID is preserved; invalid or missing values are replaced. Application request logs are JSON and contain only timestamp, level, event, request ID, method, declared route template, status, duration, and exception class. They never contain bodies, query strings, raw paths, headers, cookies, IP addresses, exception messages, or user-provided text.

Authentication security events store only keyed privacy hashes for IP and user agent and now carry the request ID. Order status history stores the actor and request ID. Audit detail keys containing address, authorization, CNIC, cookie, email, password, phone, secret, token, or URL are rejected before persistence.

Do not add PII, document locations, free-form rejection reasons, tracking numbers, or access credentials to logs, metric labels, or audit `details`. Restrict production log and audit-table access to operators with a documented support or incident-response need.

## Metrics

Set a high-entropy `METRICS_TOKEN` only in the deployment secret store. When unset, `/metrics` returns 404. When set, scrape it with `Authorization: Bearer <token>` over the private service network. Do not expose this endpoint through the public ingress.

The process exports bounded HTTP counts, cumulative request duration, in-flight requests, and staged business/security event counts. Route labels use framework templates (for example `/orders/{order_id}`), never concrete IDs. Event-label cardinality is capped.

Load `ops/prometheus/alerts.yml` into the Prometheus-compatible monitoring service. Adjust the `job` selector only if deployment service discovery uses a different stable job name; keep the thresholds under change control.

These metrics are per process and reset on restart. Aggregate all replicas in the monitoring system; the PostgreSQL audit table remains the durable source of truth.

## Immutable audit records

`audit_events` records actor, action, resource, request ID, outcome, safe metadata, and database timestamp in the same transaction as the protected change. PostgreSQL rejects every update or delete through the `audit_events_append_only` trigger. Actor IDs intentionally have no foreign key so historical accountability survives account deletion.

The initial coverage includes checkout creation, order status changes, COD settlement, wallet escrow payout, and administrative seller-verification decisions. Authentication events remain in their dedicated security-event table so lifecycle cleanup and security analysis stay separate.

## Minimum production alerts

Configure alerts in the deployment monitoring platform for:

- readiness failing for two consecutive probes;
- HTTP 5xx ratio above 2% for five minutes, split by route;
- p95 latency above the service objective for ten minutes;
- repeated authentication failures, throttling, or refresh-token reuse;
- payout, settlement, refund, or audit-write failures;
- database connection-pool exhaustion or connection errors;
- migration revision differing from the application head;
- missing metrics from any live replica.

Page immediately for payout/refund integrity failures, refresh-token reuse bursts, audit-table mutation attempts, or sustained readiness failure. Create a ticket for isolated latency or low-volume authentication anomalies.

## Incident lookup

Start from the client-visible `X-Request-ID`, find the matching structured request log, then query `auth_security_events`, `order_status_history`, and `audit_events` by `request_id`. Use actor/resource indexes for timeline reconstruction. Export only the minimum necessary fields and apply the organization's approved retention schedule; this implementation does not define legal retention policy.
