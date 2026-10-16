"""
Shopping Cart and Wishlist Router.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.models.user import User
from app.schemas.shopping import (
    CartSummary, CartItemResponse,
    WishlistSummary, WishlistItemResponse,
    AddToCartRequest, UpdateCartItemRequest, CartCheckoutRequest,
)
from app.api.deps import get_db, get_current_buyer
import app.crud.shopping as crud_shopping

router = APIRouter()


# ─── Shopping Cart ────────────────────────────────────────────────────

@router.get("/cart", response_model=CartSummary)
def get_cart(db: Session = Depends(get_db), current_user: User = Depends(get_current_buyer)):
    """Get the current user's shopping cart with all item details."""
    items = crud_shopping.get_user_cart(db, current_user.id)

    cart_items = [CartItemResponse.from_cart_item(item) for item in items]
    total_price = sum(ci.line_total for ci in cart_items)

    return CartSummary(
        items=cart_items,
        total_price=total_price,
        total_items=len(cart_items),
    )


@router.post("/cart/add")
def add_to_cart(
    payload: AddToCartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_buyer),
):
    """Add a product variant to the cart."""
    item, error = crud_shopping.add_to_cart(
        db, current_user.id, payload.product_variant_id, payload.quantity
    )
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return {"detail": "Product added to cart successfully"}


@router.delete("/cart/remove/{cart_item_id}")
def remove_from_cart(
    cart_item_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_buyer),
):
    """Remove a specific item from the cart by its cart_item_id."""
    removed = crud_shopping.remove_from_cart(db, current_user.id, cart_item_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found in your cart")
    return {"detail": "Item removed from cart"}


@router.put("/cart/item/{cart_item_id}")
def update_cart_item(
    cart_item_id: UUID,
    payload: UpdateCartItemRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_buyer),
):
    """Update the quantity of a cart item. Set to 0 to remove."""
    item, error = crud_shopping.update_cart_item_quantity(
        db, current_user.id, cart_item_id, payload.quantity
    )
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    if item is None and error is None:
        return {"detail": "Item removed from cart (quantity set to 0)"}
    return {"detail": "Cart item updated"}


@router.delete("/cart/clear")
def clear_cart(db: Session = Depends(get_db), current_user: User = Depends(get_current_buyer)):
    """Clear all items from the cart."""
    crud_shopping.clear_cart(db, current_user.id)
    return {"detail": "Cart cleared"}


@router.post("/cart/checkout")
def checkout_cart(
    payload: CartCheckoutRequest,
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
    Checkout the entire cart.
    Groups items by seller and creates a CheckoutOrder with SellerOrders.
    Delegates to the order CRUD for atomic order creation.
    """
    import app.crud.order as crud_order
    from app.models.order import PaymentMethodEnum

    # Parse payment method
    try:
        payment_method = PaymentMethodEnum(payload.payment_method)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payment method. Must be one of: {[e.value for e in PaymentMethodEnum]}"
        )

    # Delegate to order CRUD
    result = crud_order.create_order_from_cart(
        db=db,
        buyer_id=current_user.id,
        shipping_address_id=payload.shipping_address_id,
        payment_method=payment_method,
        idempotency_key=idempotency_key,
    )

    if isinstance(result, str):
        # Error message returned
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result)

    return {
        "detail": f"Order placed successfully",
        "order_id": str(result.id),
        "total_amount": result.total_amount,
        "seller_orders_count": len(result.seller_orders),
    }


# ─── Wishlist ─────────────────────────────────────────────────────────

@router.get("/wishlist", response_model=WishlistSummary)
def get_wishlist(db: Session = Depends(get_db), current_user: User = Depends(get_current_buyer)):
    """Get the current user's wishlist."""
    items = crud_shopping.get_user_wishlist(db, current_user.id)
    wishlist_items = [WishlistItemResponse.from_wishlist_item(item) for item in items]
    return WishlistSummary(
        items=wishlist_items,
        total_items=len(wishlist_items),
    )


@router.post("/wishlist/toggle/{product_id}")
def toggle_wishlist(
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_buyer),
):
    """Toggle a product in the wishlist (adds if missing, removes if present)."""
    added, message = crud_shopping.toggle_wishlist(db, current_user.id, product_id)
    return {"detail": message, "is_in_wishlist": added}
