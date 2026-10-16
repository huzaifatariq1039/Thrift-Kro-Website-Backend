"""Authoritative platform reporting metrics for the administrator dashboard."""

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.money import ZERO_MONEY, money
from app.models.order import (
    CheckoutOrder,
    OrderPayment,
    OrderStatusEnum,
    PaymentStatusEnum,
    SellerOrder,
)
from app.models.product import Product, ProductStatusEnum
from app.models.support import SupportTicket, TicketStatusEnum
from app.models.user import RoleEnum, SellerProfile, User, VerificationStatusEnum
from app.schemas.admin_reporting import AdminStatsResponse


SUCCESSFUL_ORDER_STATUSES = (
    OrderStatusEnum.COMPLETED,
    OrderStatusEnum.COMPLETED_PAYOUT,
)
OPEN_ORDER_STATUSES = (
    OrderStatusEnum.PENDING_PAYMENT,
    OrderStatusEnum.PAID_FUNDS_IN_ESCROW,
    OrderStatusEnum.PROCESSING,
    OrderStatusEnum.SHIPPED,
    OrderStatusEnum.DELIVERED,
    OrderStatusEnum.DISPUTED,
)


def _count(db: Session, column, *criteria) -> int:
    return int(db.query(func.count(column)).filter(*criteria).scalar() or 0)


def _sum_money(db: Session, column, *criteria):
    return money(db.query(func.sum(column)).filter(*criteria).scalar() or ZERO_MONEY)


def get_platform_stats(db: Session) -> AdminStatsResponse:
    """Return non-overlapping order counts and settlement-backed financial metrics."""
    total_users = _count(db, User.id)
    total_buyers = _count(db, User.id, User.role == RoleEnum.BUYER)
    total_sellers = _count(db, User.id, User.role == RoleEnum.SELLER)
    total_admins = _count(db, User.id, User.role == RoleEnum.ADMIN)
    verified_sellers = _count(
        db,
        SellerProfile.id,
        SellerProfile.is_verified.is_(True),
    )
    pending_verifications = _count(
        db,
        SellerProfile.id,
        SellerProfile.verification_status == VerificationStatusEnum.PENDING,
    )

    total_products = _count(db, Product.id)
    live_products = _count(
        db,
        Product.id,
        Product.status == ProductStatusEnum.AVAILABLE,
        Product.deleted_at.is_(None),
    )
    out_of_stock_products = _count(
        db,
        Product.id,
        Product.status == ProductStatusEnum.OUT_OF_STOCK,
        Product.deleted_at.is_(None),
    )
    draft_products = _count(
        db,
        Product.id,
        Product.status == ProductStatusEnum.DRAFT,
        Product.deleted_at.is_(None),
    )
    archived_products = _count(
        db,
        Product.id,
        or_(
            Product.status == ProductStatusEnum.ARCHIVED,
            Product.deleted_at.is_not(None),
        ),
    )

    total_checkouts = _count(db, CheckoutOrder.id)
    total_seller_orders = _count(db, SellerOrder.id)
    open_checkouts = int(
        db.query(func.count(func.distinct(SellerOrder.checkout_order_id)))
        .filter(SellerOrder.status.in_(OPEN_ORDER_STATUSES))
        .scalar()
        or 0
    )
    completed_checkouts = _count(
        db,
        CheckoutOrder.id,
        CheckoutOrder.seller_orders.any(),
        ~CheckoutOrder.seller_orders.any(
            SellerOrder.status.notin_(SUCCESSFUL_ORDER_STATUSES)
        ),
    )
    closed_checkouts = max(total_checkouts - open_checkouts - completed_checkouts, 0)

    settled_gmv = money(
        db.query(func.sum(SellerOrder.subtotal))
        .join(OrderPayment, OrderPayment.seller_order_id == SellerOrder.id)
        .filter(OrderPayment.status == PaymentStatusEnum.SETTLED)
        .scalar()
        or ZERO_MONEY
    )
    settled_payment_volume = _sum_money(
        db,
        OrderPayment.amount,
        OrderPayment.status == PaymentStatusEnum.SETTLED,
    )
    recognized_revenue = _sum_money(
        db,
        OrderPayment.platform_fee,
        OrderPayment.status == PaymentStatusEnum.SETTLED,
    )
    escrow_held = _sum_money(
        db,
        OrderPayment.amount,
        OrderPayment.status == PaymentStatusEnum.HELD,
    )
    pending_payment_value = _sum_money(
        db,
        OrderPayment.amount,
        OrderPayment.status == PaymentStatusEnum.PENDING,
    )

    open_tickets = _count(
        db,
        SupportTicket.id,
        SupportTicket.status.in_(
            (TicketStatusEnum.OPEN, TicketStatusEnum.IN_PROGRESS)
        ),
    )

    return AdminStatsResponse(
        users={
            "total_users": total_users,
            "buyers": total_buyers,
            "sellers": total_sellers,
            "admins": total_admins,
            "verified_sellers": verified_sellers,
            "pending_verifications": pending_verifications,
        },
        products={
            "total_products": total_products,
            "live_available": live_products,
            "out_of_stock": out_of_stock_products,
            "draft": draft_products,
            "archived": archived_products,
        },
        orders={
            "total_checkout_orders": total_checkouts,
            "open_checkout_orders": open_checkouts,
            "completed_checkout_orders": completed_checkouts,
            "closed_checkout_orders": closed_checkouts,
            "total_seller_orders": total_seller_orders,
        },
        revenue={
            "settled_gmv_pkr": settled_gmv,
            "settled_payment_volume_pkr": settled_payment_volume,
            "recognized_platform_revenue_pkr": recognized_revenue,
            "escrow_held_pkr": escrow_held,
            "pending_payment_value_pkr": pending_payment_value,
        },
        support={"open_tickets": open_tickets},
    )
