"""Typed contracts for financially meaningful administrator metrics."""

from decimal import Decimal

from pydantic import BaseModel


class AdminUserMetrics(BaseModel):
    total_users: int
    buyers: int
    sellers: int
    admins: int
    verified_sellers: int
    pending_verifications: int


class AdminProductMetrics(BaseModel):
    total_products: int
    live_available: int
    out_of_stock: int
    draft: int
    archived: int


class AdminOrderMetrics(BaseModel):
    total_checkout_orders: int
    open_checkout_orders: int
    completed_checkout_orders: int
    closed_checkout_orders: int
    total_seller_orders: int


class AdminRevenueMetrics(BaseModel):
    settled_gmv_pkr: Decimal
    settled_payment_volume_pkr: Decimal
    recognized_platform_revenue_pkr: Decimal
    escrow_held_pkr: Decimal
    pending_payment_value_pkr: Decimal


class AdminSupportMetrics(BaseModel):
    open_tickets: int


class AdminStatsResponse(BaseModel):
    users: AdminUserMetrics
    products: AdminProductMetrics
    orders: AdminOrderMetrics
    revenue: AdminRevenueMetrics
    support: AdminSupportMetrics
