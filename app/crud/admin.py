from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.user import User, SellerProfile, VerificationStatusEnum, Wallet, Transaction, RoleEnum
from app.models.product import Product, ProductStatusEnum
from app.models.support import SupportTicket, TicketStatusEnum
from app.models.order import CheckoutOrder, SellerOrder, OrderStatusEnum
from app.models.verification import VerificationLog
from app.schemas.admin import AdminStatsResponse


def get_platform_stats(db: Session) -> AdminStatsResponse:
    # Users Stats
    total_buyers = db.query(func.count(User.id)).filter(User.role == RoleEnum.BUYER).scalar() or 0
    total_sellers = db.query(func.count(User.id)).filter(User.role == RoleEnum.SELLER).scalar() or 0
    total_verified_sellers = db.query(func.count(SellerProfile.id)).filter(SellerProfile.is_verified == True).scalar() or 0

    # Products Stats
    total_available_products = db.query(func.count(Product.id)).filter(Product.status == StatusEnum.AVAILABLE).scalar() or 0
    total_sold_products = db.query(func.count(Product.id)).filter(Product.status == StatusEnum.SOLD).scalar() or 0

    # Orders Stats
    total_completed_orders = db.query(func.count(SellerOrder.id)).filter(SellerOrder.status == OrderStatusEnum.COMPLETED_PAYOUT).scalar() or 0
    total_pending_orders = db.query(func.count(SellerOrder.id)).filter(SellerOrder.status != OrderStatusEnum.COMPLETED_PAYOUT).scalar() or 0

    # Revenue Stats (Sum of escrow fees on non-failed orders)
    # Exclude PENDING, and DISPUTED to be safe. We only count revenue from ESCROW, SHIPPED, DELIVERED, and COMPLETED
    valid_revenue_statuses = [
        OrderStatusEnum.FUNDS_IN_ESCROW, 
        OrderStatusEnum.SHIPPED, 
        OrderStatusEnum.DELIVERED, 
        OrderStatusEnum.COMPLETED_PAYOUT
    ]
    
    total_platform_revenue = db.query(func.sum(SellerOrder.platform_fee)).filter(SellerOrder.status.in_(valid_revenue_statuses)).scalar() or 0.0
    total_gmv = db.query(func.sum(CheckoutOrder.total_amount)).filter(CheckoutOrder.status.in_(valid_revenue_statuses)).scalar() or 0.0

    return AdminStatsResponse(
        users={
            "total_buyers": total_buyers,
            "total_sellers": total_sellers,
            "verified_sellers": total_verified_sellers,
            "total_users": total_buyers + total_sellers
        },
        products={
            "live_available": total_available_products,
            "sold": total_sold_products,
            "total_products": total_available_products + total_sold_products
        },
        orders={
            "completed": total_completed_orders,
            "in_progress": total_pending_orders,
            "total_orders": total_completed_orders + total_pending_orders
        },
        revenue={
            "total_platform_revenue_pkr": total_platform_revenue,
            "gross_merchandise_value_pkr": total_gmv
        }
    )
