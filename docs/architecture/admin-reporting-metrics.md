# Administrator reporting metric contract

All dashboard values are lifetime snapshots in PKR unless a reporting period is
explicitly added to the API. The dashboard must not manufacture time-series or
derive one financial balance from another metric.

## Order units

- `total_checkout_orders` counts buyer checkout records. One multi-vendor
  checkout is one order.
- `total_seller_orders` separately counts vendor fulfillment units and must not
  be presented as customer orders.
- `open_checkout_orders` counts distinct checkouts with at least one nonterminal
  seller order.
- `completed_checkout_orders` counts checkouts only when every seller order has
  completed successfully.
- `closed_checkout_orders` is the remaining terminal population, including
  cancelled, refunded, and mixed terminal outcomes. These three checkout
  categories are non-overlapping and sum to `total_checkout_orders`.

## Financial units

- `settled_gmv_pkr` is settled merchandise subtotal. It excludes shipping and
  platform fees.
- `settled_payment_volume_pkr` is the full amount of settled payment
  allocations, including merchandise, shipping, and platform fees.
- `recognized_platform_revenue_pkr` is the platform fee on `SETTLED` payment
  allocations only. Held, pending, refunded, and cancelled payments are not
  revenue.
- `escrow_held_pkr` is the full amount of payment allocations currently in the
  `HELD` state.
- `pending_payment_value_pkr` is operational pipeline value, not collected cash,
  GMV, revenue, or escrow.

The `order_payments` lifecycle is the reporting source because it records the
settlement/refund state for wallet and cash-on-delivery orders. Wallet settlement
continues to be backed by the immutable ledger; no reporting query mutates
payment or ledger state.
