# Shopping session policy

## Launch contract

Cart and wishlist operations are available only to authenticated users with the
buyer role. The active website applies the same buyer-only route guard, so the
API does not create anonymous browser identities or silently persist guest
shopping data.

Each buyer has one cart session. Adding the same product variant increments the
existing line atomically, and the database prevents duplicate cart and wishlist
rows. Wishlist toggles are serialized per buyer so concurrent requests behave
like ordered toggles.

## Guest carts

Guest carts are deferred and are not a launch requirement. This is an explicit
product boundary, not an incomplete authenticated-cart implementation. A future
guest-cart release must define and test all of the following before exposing an
anonymous API:

- an opaque, high-entropy cart identifier stored in a secure cookie;
- expiry and scheduled cleanup without collecting unnecessary personal data;
- rate limits and limits on distinct lines and quantities;
- a transactional sign-in merge rule that respects current stock and the
  authenticated cart's existing quantities;
- identifier rotation after sign-in to prevent cart fixation;
- frontend behavior for merge conflicts, expired carts, and unavailable items.

Checkout remains authenticated and revalidates stock inside its own database
transaction. Cart contents never reserve inventory.
