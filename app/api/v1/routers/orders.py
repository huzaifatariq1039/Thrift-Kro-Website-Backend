"""
Orders Router — checkout, order management, and escrow operations.

Buyer endpoints:  POST /checkout, GET /, GET /{id}, POST /{id}/release-escrow
Seller endpoints: GET /seller, GET /seller/{id}, PUT /seller/{id}/status
Admin endpoints:  GET /all (via admin router)
"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.schemas.order import OrderCreate, OrderResponse, OrderStatusUpdate, SellerOrderSchema
from app.models.user import User, RoleEnum
from app.models.order import OrderStatusEnum
import app.crud.order as crud_order
from app.api.deps import get_db, get_current_active_user, get_current_buyer, get_current_seller

router = APIRouter()


# ─── Buyer Endpoints ─────────────────────────────────────────────────

@router.post("/checkout", response_model=OrderResponse)
def checkout(
    order: OrderCreate,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_buyer),
):
    """
    Create an order from the buyer's cart.
    Groups items by seller, calculates fees, processes payment.
    """
    result = crud_order.create_order_from_cart(
        db=db,
        buyer_id=current_user.id,
        shipping_address_id=order.shipping_address_id,
        payment_method=order.payment_method,
        idempotency_key=idempotency_key,
    )

    if isinstance(result, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result)

    return result


@router.get("/", response_model=List[OrderResponse])
def get_my_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get all orders for the current buyer."""
    return crud_order.get_orders_by_user(db=db, user_id=current_user.id, is_seller=False)


@router.get("/seller", response_model=List[SellerOrderSchema])
def get_seller_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_seller),
):
    """Get all orders received by the current seller."""
    return crud_order.get_orders_by_user(db=db, user_id=current_user.id, is_seller=True)


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single order by ID. Only the buyer or involved seller can view."""
    order = crud_order.get_order(db, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Authorization: only buyer, involved seller, or admin can view
    is_buyer = order.buyer_id == current_user.id
    is_seller = any(so.seller_id == current_user.id for so in order.seller_orders)
    is_admin = current_user.role == RoleEnum.ADMIN

    if not (is_buyer or is_seller or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized to view this order")

    return order


@router.get("/seller/{seller_order_id}", response_model=SellerOrderSchema)
def get_seller_order_detail(
    seller_order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single seller order by ID."""
    seller_order = crud_order.get_seller_order(db, seller_order_id=seller_order_id)
    if not seller_order:
        raise HTTPException(status_code=404, detail="Seller order not found")

    # Authorization
    checkout = seller_order.checkout_order
    is_buyer = checkout and checkout.buyer_id == current_user.id
    is_seller = seller_order.seller_id == current_user.id
    is_admin = current_user.role == RoleEnum.ADMIN

    if not (is_buyer or is_seller or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized to view this order")

    return seller_order


# ─── Seller Status Updates ───────────────────────────────────────────

@router.put("/seller/{seller_order_id}/status", response_model=SellerOrderSchema)
def update_order_status(
    seller_order_id: UUID,
    update: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Update the status of a seller order.
    Sellers can: PROCESSING, SHIPPED (with tracking)
    Buyers can: confirm DELIVERED
    Admin can: any valid transition
    """
    # Get the order to check authorization
    seller_order = crud_order.get_seller_order(db, seller_order_id)
    if not seller_order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Authorization
    is_seller = seller_order.seller_id == current_user.id
    is_buyer = seller_order.checkout_order and seller_order.checkout_order.buyer_id == current_user.id
    is_admin = current_user.role == RoleEnum.ADMIN

    # Sellers can only set PROCESSING, SHIPPED
    seller_allowed = [OrderStatusEnum.PROCESSING, OrderStatusEnum.SHIPPED]
    # Buyers can only confirm DELIVERED
    buyer_allowed = [OrderStatusEnum.DELIVERED]

    if is_admin:
        pass  # Admin can do anything
    elif is_seller and update.status in seller_allowed:
        pass
    elif is_buyer and update.status in buyer_allowed:
        pass
    else:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to make this status change",
        )

    result = crud_order.update_order_status(
        db=db,
        seller_order_id=seller_order_id,
        new_status=update.status,
        actor_id=current_user.id,
        tracking_number=update.tracking_number,
        courier_name=update.courier_name,
        notes=update.notes,
    )

    if isinstance(result, str):
        raise HTTPException(status_code=400, detail=result)

    return result


# ─── Payment Settlement ──────────────────────────────────────────────

@router.post("/seller/{seller_order_id}/release-escrow", response_model=SellerOrderSchema)
def release_escrow(
    seller_order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Complete a delivered order's payment settlement.
    Wallet orders release escrow; COD orders record collection completion.
    """
    seller_order = crud_order.get_seller_order(db, seller_order_id)
    if not seller_order:
        raise HTTPException(status_code=404, detail="Order not found")

    is_buyer = seller_order.checkout_order and seller_order.checkout_order.buyer_id == current_user.id
    is_admin = current_user.role == RoleEnum.ADMIN

    if not (is_buyer or is_admin):
        raise HTTPException(
            status_code=403,
            detail="Only the buyer or admin can release escrow funds",
        )

    if seller_order.status == OrderStatusEnum.DISPUTED and not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Only an admin can settle a disputed order",
        )

    result = crud_order.release_escrow(
        db=db,
        seller_order_id=seller_order_id,
        actor_id=current_user.id,
    )

    if isinstance(result, str):
        raise HTTPException(status_code=400, detail=result)

    return result
