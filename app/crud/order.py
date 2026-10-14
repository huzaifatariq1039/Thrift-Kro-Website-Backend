"""
CRUD operations for Orders — multi-vendor checkout, status management, and escrow.

All write operations use atomic transactions with rollback on failure.

Order Flow:
  1. Buyer checks out cart → CheckoutOrder created, grouped into SellerOrders
  2. Payment processed (Wallet/COD) → status → PAID_FUNDS_IN_ESCROW or PENDING_PAYMENT
  3. Seller processes → PROCESSING → SHIPPED (with tracking) → DELIVERED
  4. Buyer confirms → release_escrow → COMPLETED_PAYOUT (seller credited)
"""
from datetime import datetime, timezone
from collections import defaultdict
from typing import List, Optional, Union

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from uuid import UUID

from app.models.order import (
    CheckoutOrder, SellerOrder, OrderItem, OrderStatusHistory,
    PaymentMethodEnum, OrderStatusEnum,
)
from app.models.shopping import CartSession, CartItem
from app.models.product import Product, ProductStatusEnum, ProductVariant
from app.models.user import User, Wallet, Transaction, TransactionTypeEnum, UserAddress


# ─── Constants ────────────────────────────────────────────────────────

PLATFORM_FEE_RATE = 0.05  # 5% platform fee
FLAT_SHIPPING_FEE = 200.0  # PKR flat rate per seller order

# Valid status transitions (state machine)
VALID_TRANSITIONS = {
    OrderStatusEnum.PENDING_PAYMENT: [OrderStatusEnum.PAID_FUNDS_IN_ESCROW, OrderStatusEnum.CANCELLED],
    OrderStatusEnum.PAID_FUNDS_IN_ESCROW: [OrderStatusEnum.PROCESSING, OrderStatusEnum.CANCELLED, OrderStatusEnum.REFUNDED],
    OrderStatusEnum.PROCESSING: [OrderStatusEnum.SHIPPED, OrderStatusEnum.CANCELLED],
    OrderStatusEnum.SHIPPED: [OrderStatusEnum.DELIVERED, OrderStatusEnum.DISPUTED],
    OrderStatusEnum.DELIVERED: [OrderStatusEnum.COMPLETED_PAYOUT, OrderStatusEnum.DISPUTED],
    OrderStatusEnum.COMPLETED_PAYOUT: [],  # Terminal state
    OrderStatusEnum.CANCELLED: [],  # Terminal state
    OrderStatusEnum.DISPUTED: [OrderStatusEnum.REFUNDED, OrderStatusEnum.COMPLETED_PAYOUT],
    OrderStatusEnum.REFUNDED: [],  # Terminal state
}


# ─── Helpers ──────────────────────────────────────────────────────────

def _build_order_response(order: CheckoutOrder) -> CheckoutOrder:
    """Eagerly load all relationships for the response."""
    # The order is already loaded with relationships via joinedload
    return order


def _compute_overall_status(seller_orders: list) -> str:
    """Determine an aggregate status from all seller sub-orders."""
    if not seller_orders:
        return "UNKNOWN"

    statuses = [so.status for so in seller_orders]

    # If all completed
    if all(s == OrderStatusEnum.COMPLETED_PAYOUT for s in statuses):
        return "COMPLETED"
    # If any disputed
    if any(s == OrderStatusEnum.DISPUTED for s in statuses):
        return "DISPUTED"
    # If any shipped
    if any(s == OrderStatusEnum.SHIPPED for s in statuses):
        return "SHIPPED"
    # If any processing
    if any(s == OrderStatusEnum.PROCESSING for s in statuses):
        return "PROCESSING"
    # If all cancelled
    if all(s == OrderStatusEnum.CANCELLED for s in statuses):
        return "CANCELLED"
    # Default
    return statuses[0].value if statuses else "PENDING"


# ─── Create Order ─────────────────────────────────────────────────────

def create_order_from_cart(
    db: Session,
    buyer_id: UUID,
    shipping_address_id: Optional[UUID],
    payment_method: PaymentMethodEnum,
    idempotency_key: str,
) -> Union[CheckoutOrder, str]:
    """
    Create a multi-vendor order from the buyer's cart.

    Steps:
      1. Validate cart is not empty
      2. Validate shipping address (if provided) belongs to buyer
      3. Group cart items by seller
      4. Atomically: create CheckoutOrder + SellerOrders + OrderItems
      5. Process payment (wallet deduction if applicable)
      6. Decrement stock
      7. Clear cart
      8. Return the created order

    Returns CheckoutOrder on success, or error message string on failure.
    """
    try:
        idempotency_key = idempotency_key.strip()
        existing_order = (
            db.query(CheckoutOrder)
            .filter(
                CheckoutOrder.buyer_id == buyer_id,
                CheckoutOrder.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing_order:
            return get_order(db, existing_order.id)

        # 1. Get cart items
        cart_session = (
            db.query(CartSession)
            .filter(CartSession.user_id == buyer_id)
            .with_for_update()
            .first()
        )
        if not cart_session:
            return "Your cart is empty"

        # A concurrent request with the same key may have completed while this
        # request waited for the buyer's cart lock.
        existing_order = (
            db.query(CheckoutOrder)
            .filter(
                CheckoutOrder.buyer_id == buyer_id,
                CheckoutOrder.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing_order:
            return get_order(db, existing_order.id)

        cart_items = (
            db.query(CartItem)
            .filter(CartItem.cart_session_id == cart_session.id)
            .order_by(CartItem.id)
            .with_for_update()
            .all()
        )

        if not cart_items:
            return "Your cart is empty"

        variant_ids = sorted({item.product_variant_id for item in cart_items}, key=str)
        locked_variants = (
            db.query(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .filter(ProductVariant.id.in_(variant_ids))
            .order_by(ProductVariant.id)
            .with_for_update(of=ProductVariant)
            .all()
        )
        variants_by_id = {variant.id: variant for variant in locked_variants}
        required_stock = defaultdict(int)
        for cart_item in cart_items:
            required_stock[cart_item.product_variant_id] += cart_item.quantity

        # 2. Validate shipping address ownership
        if shipping_address_id:
            address = db.query(UserAddress).filter(
                UserAddress.id == shipping_address_id,
                UserAddress.user_id == buyer_id,
            ).first()
            if not address:
                return "Shipping address not found or does not belong to you"

        # 3. Group items by seller
        seller_groups = defaultdict(list)
        for cart_item in cart_items:
            variant = variants_by_id.get(cart_item.product_variant_id)
            if not variant or not variant.product:
                return "A cart item is no longer available"
            product = variant.product
            if product.deleted_at is not None:
                return f"Product '{product.name}' is no longer available"
            if product.status != ProductStatusEnum.AVAILABLE:
                return f"Product '{product.name}' is not available for checkout"
            seller_groups[product.seller_id].append((cart_item, variant, product))

        for variant_id, requested_quantity in required_stock.items():
            variant = variants_by_id[variant_id]
            if variant.quantity_in_stock < requested_quantity:
                return (
                    f"Insufficient stock for '{variant.product.name}'. "
                    f"Only {variant.quantity_in_stock} available"
                )

        if not seller_groups:
            return "No valid items in cart"

        # 4. Calculate totals
        grand_total = 0.0
        seller_data = []

        for seller_id, items in seller_groups.items():
            subtotal = 0.0
            for cart_item, variant, product in items:
                unit_price = product.price + variant.price_adjustment
                subtotal += unit_price * cart_item.quantity

            shipping_fee = FLAT_SHIPPING_FEE
            platform_fee = round(subtotal * PLATFORM_FEE_RATE, 2)
            total = round(subtotal + shipping_fee + platform_fee, 2)
            grand_total += total

            seller_data.append({
                "seller_id": seller_id,
                "items": items,
                "subtotal": subtotal,
                "shipping_fee": shipping_fee,
                "platform_fee": platform_fee,
                "total": total,
            })

        grand_total = round(grand_total, 2)

        # 5. Wallet payment validation
        initial_status = OrderStatusEnum.PENDING_PAYMENT

        wallet = None
        if payment_method == PaymentMethodEnum.WALLET:
            wallet = (
                db.query(Wallet)
                .filter(Wallet.user_id == buyer_id)
                .with_for_update()
                .first()
            )
            if not wallet:
                return "Wallet not found. Please set up your wallet first"
            if wallet.balance < grand_total:
                return f"Insufficient wallet balance. Need PKR {grand_total}, have PKR {wallet.balance}"
            initial_status = OrderStatusEnum.PAID_FUNDS_IN_ESCROW

        # 6. Create CheckoutOrder (atomic from here)
        checkout_order = CheckoutOrder(
            buyer_id=buyer_id,
            total_amount=grand_total,
            payment_method=payment_method,
            shipping_address_id=shipping_address_id,
            idempotency_key=idempotency_key,
        )
        db.add(checkout_order)
        db.flush()

        # 7. Create SellerOrders and OrderItems
        for sd in seller_data:
            seller_order = SellerOrder(
                checkout_order_id=checkout_order.id,
                seller_id=sd["seller_id"],
                subtotal=sd["subtotal"],
                shipping_fee=sd["shipping_fee"],
                platform_fee=sd["platform_fee"],
                total_amount=sd["total"],
                status=initial_status,
            )
            db.add(seller_order)
            db.flush()

            # Record initial status
            db.add(OrderStatusHistory(
                seller_order_id=seller_order.id,
                status=initial_status,
                notes="Order created",
            ))

            for cart_item, variant, product in sd["items"]:
                unit_price = product.price + variant.price_adjustment

                db.add(OrderItem(
                    seller_order_id=seller_order.id,
                    product_variant_id=variant.id,
                    price_at_purchase=unit_price,
                    quantity=cart_item.quantity,
                ))

        # Decrement each locked variant once using the aggregated cart quantity.
        for variant_id, requested_quantity in required_stock.items():
            variants_by_id[variant_id].quantity_in_stock -= requested_quantity

        # 8. Process wallet payment
        if payment_method == PaymentMethodEnum.WALLET:
            wallet.balance -= grand_total
            wallet.balance = round(wallet.balance, 2)

            db.add(Transaction(
                wallet_id=wallet.id,
                type=TransactionTypeEnum.PAYMENT,
                amount=-grand_total,
                reference_id=checkout_order.id,
                reference_type="checkout_order",
                status="COMPLETED",
                description=f"Payment for order {checkout_order.id}",
            ))

        # 9. Clear cart
        db.query(CartItem).filter(CartItem.cart_session_id == cart_session.id).delete()

        # 10. Commit everything
        db.commit()

        # Return fully loaded order
        return get_order(db, checkout_order.id)

    except IntegrityError:
        db.rollback()
        existing_order = (
            db.query(CheckoutOrder)
            .filter(
                CheckoutOrder.buyer_id == buyer_id,
                CheckoutOrder.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing_order:
            return get_order(db, existing_order.id)
        raise
    except Exception:
        db.rollback()
        raise


# ─── Read Orders ──────────────────────────────────────────────────────

def get_order(db: Session, order_id: UUID) -> Optional[CheckoutOrder]:
    """Get a single checkout order with all nested relationships."""
    return (
        db.query(CheckoutOrder)
        .options(
            joinedload(CheckoutOrder.seller_orders)
            .joinedload(SellerOrder.order_items)
            .joinedload(OrderItem.product_variant)
            .joinedload(ProductVariant.product),
            joinedload(CheckoutOrder.seller_orders)
            .joinedload(SellerOrder.seller),
        )
        .filter(CheckoutOrder.id == order_id)
        .first()
    )


def get_orders_by_user(
    db: Session, user_id: UUID, is_seller: bool = False
) -> list:
    """Get orders for a user. Buyers see CheckoutOrders, sellers see SellerOrders."""
    if is_seller:
        return (
            db.query(SellerOrder)
            .options(
                joinedload(SellerOrder.order_items)
                .joinedload(OrderItem.product_variant)
                .joinedload(ProductVariant.product),
                joinedload(SellerOrder.checkout_order),
            )
            .filter(SellerOrder.seller_id == user_id)
            .order_by(SellerOrder.created_at.desc())
            .all()
        )
    else:
        return (
            db.query(CheckoutOrder)
            .options(
                joinedload(CheckoutOrder.seller_orders)
                .joinedload(SellerOrder.order_items),
                joinedload(CheckoutOrder.seller_orders)
                .joinedload(SellerOrder.seller),
            )
            .filter(CheckoutOrder.buyer_id == user_id)
            .order_by(CheckoutOrder.created_at.desc())
            .all()
        )


def get_seller_order(db: Session, seller_order_id: UUID) -> Optional[SellerOrder]:
    """Get a single seller order."""
    return (
        db.query(SellerOrder)
        .options(
            joinedload(SellerOrder.order_items)
            .joinedload(OrderItem.product_variant)
            .joinedload(ProductVariant.product),
            joinedload(SellerOrder.checkout_order),
            joinedload(SellerOrder.status_history),
        )
        .filter(SellerOrder.id == seller_order_id)
        .first()
    )


# ─── Update Order Status ─────────────────────────────────────────────

def update_order_status(
    db: Session,
    seller_order_id: UUID,
    new_status: OrderStatusEnum,
    actor_id: UUID,
    tracking_number: Optional[str] = None,
    courier_name: Optional[str] = None,
    notes: Optional[str] = None,
) -> Union[SellerOrder, str]:
    """
    Update the status of a seller order with state machine validation.
    Returns the updated SellerOrder or an error message.
    """
    try:
        seller_order = db.query(SellerOrder).filter(SellerOrder.id == seller_order_id).first()
        if not seller_order:
            return "Order not found"

        # Validate state transition
        allowed = VALID_TRANSITIONS.get(seller_order.status, [])
        if new_status not in allowed:
            return (
                f"Cannot transition from {seller_order.status.value} to {new_status.value}. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )

        now = datetime.now(timezone.utc)

        # Apply status-specific logic
        seller_order.status = new_status

        if new_status == OrderStatusEnum.SHIPPED:
            seller_order.shipped_at = now
            if tracking_number:
                seller_order.tracking_number = tracking_number
            if courier_name:
                seller_order.courier_name = courier_name

        elif new_status == OrderStatusEnum.DELIVERED:
            seller_order.delivered_at = now

        # Record in status history
        db.add(OrderStatusHistory(
            seller_order_id=seller_order.id,
            status=new_status,
            notes=notes or f"Status updated to {new_status.value}",
        ))

        db.commit()
        return get_seller_order(db, seller_order_id)

    except Exception:
        db.rollback()
        raise


# ─── Release Escrow ───────────────────────────────────────────────────

def release_escrow(db: Session, seller_order_id: UUID, actor_id: UUID) -> Union[SellerOrder, str]:
    """
    Release escrowed funds to the seller after delivery confirmation.

    Only works when:
      - Order status is DELIVERED
      - Payment method was WALLET (funds are in escrow)

    Steps:
      1. Credit seller wallet with (subtotal - platform_fee)
      2. Create Transaction records
      3. Update status to COMPLETED_PAYOUT
    """
    try:
        seller_order = (
            db.query(SellerOrder)
            .options(joinedload(SellerOrder.checkout_order))
            .filter(SellerOrder.id == seller_order_id)
            .first()
        )

        if not seller_order:
            return "Order not found"

        if seller_order.status != OrderStatusEnum.DELIVERED:
            return f"Escrow can only be released for DELIVERED orders. Current status: {seller_order.status.value}"

        checkout = seller_order.checkout_order
        if checkout.payment_method != PaymentMethodEnum.WALLET:
            # For COD, mark as completed without wallet transfers
            seller_order.status = OrderStatusEnum.COMPLETED_PAYOUT
            db.add(OrderStatusHistory(
                seller_order_id=seller_order.id,
                status=OrderStatusEnum.COMPLETED_PAYOUT,
                notes="Completed (Cash on Delivery)",
            ))
            db.commit()
            return get_seller_order(db, seller_order_id)

        # Calculate seller payout
        seller_payout = round(seller_order.subtotal + seller_order.shipping_fee, 2)

        # Credit seller wallet
        seller_wallet = db.query(Wallet).filter(Wallet.user_id == seller_order.seller_id).first()
        if not seller_wallet:
            return "Seller wallet not found"

        seller_wallet.balance += seller_payout
        seller_wallet.balance = round(seller_wallet.balance, 2)

        # Record seller credit transaction
        db.add(Transaction(
            wallet_id=seller_wallet.id,
            type=TransactionTypeEnum.ESCROW_RELEASE,
            amount=seller_payout,
            reference_id=seller_order.id,
            reference_type="seller_order",
            status="COMPLETED",
            description=f"Escrow release for order {seller_order.id}",
        ))

        # Update status
        seller_order.status = OrderStatusEnum.COMPLETED_PAYOUT
        db.add(OrderStatusHistory(
            seller_order_id=seller_order.id,
            status=OrderStatusEnum.COMPLETED_PAYOUT,
            notes="Escrow released to seller",
        ))

        db.commit()
        return get_seller_order(db, seller_order_id)

    except Exception:
        db.rollback()
        raise
