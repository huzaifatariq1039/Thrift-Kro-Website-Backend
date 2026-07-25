"""
Shopping Cart and Wishlist Router.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.models.user import User
from app.models.order import PaymentMethodEnum
from app.schemas.shopping import CartSummary, WishlistSummary
from app.api.deps import get_db, get_current_active_user
import app.crud.shopping as crud_shopping
import app.crud.order as crud_order

router = APIRouter()


# --- Shopping Cart ---

@router.get("/cart", response_model=CartSummary)
def get_cart(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Get the current user's shopping cart."""
    items = crud_shopping.get_user_cart(db, current_user.id)
    total_price = sum(item.product.price for item in items if item.product)
    
    return CartSummary(
        items=items,
        total_price=total_price,
        total_items=len(items)
    )


@router.post("/cart/add/{product_id}")
def add_to_cart(product_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Add a product to the cart. Marks the product as IN_CART."""
    item, error = crud_shopping.add_to_cart(db, current_user.id, product_id)
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return {"detail": "Product added to cart successfully"}


@router.delete("/cart/remove/{product_id}")
def remove_from_cart(product_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Remove a product from the cart. Marks the product as AVAILABLE."""
    removed = crud_shopping.remove_from_cart(db, current_user.id, product_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found in your cart")
    return {"detail": "Product removed from cart"}


@router.post("/cart/checkout")
def checkout_cart(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Checkout the entire cart.
    Since this is a C2C platform, this converts each CartItem into a separate Order.
    Requires sufficient wallet balance for the total cart amount.
    """
    items = crud_shopping.get_user_cart(db, current_user.id)
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your cart is empty")
        
    total_cart_price = sum(item.product.price for item in items if item.product)
    
    # Calculate total with fees (assuming flat shipping fee + standard escrow fee per item)
    # This logic mimics what crud_order.create_order does, but we need to check the total 
    # wallet balance beforehand.
    total_amount_needed = 0.0
    for item in items:
        if not item.product:
            continue
        price = item.product.price
        escrow_fee = price * 0.05
        shipping_fee = 200.0  # standard shipping fee in this app
        total_amount_needed += (price + escrow_fee + shipping_fee)
        
    if current_user.wallet and current_user.wallet.balance < total_amount_needed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Insufficient funds. Your balance is {current_user.wallet.balance}, but you need {total_amount_needed}."
        )
        
    created_orders = []
    from app.schemas.order import OrderCreate
    
    # Process each item
    for item in items:
        if not item.product:
            continue
            
        order_create = OrderCreate(
            product_id=item.product.id,
            shipping_address="Saved User Address", # In a real app, this comes from the checkout request
            payment_method=PaymentMethodEnum.WALLET
        )
        
        # This will deduct from wallet and mark product as SOLD
        db_order = crud_order.create_order(db=db, order=order_create, buyer_id=current_user.id)
        if db_order and db_order != "INSUFFICIENT_FUNDS":
            created_orders.append(db_order.id)
            
    # Clear the cart (items successfully ordered are now SOLD, so we just remove cart records)
    for item in items:
        db.delete(item)
    db.commit()
    
    return {
        "detail": f"Successfully checked out {len(created_orders)} items",
        "order_ids": created_orders
    }


# --- Wishlist ---

@router.get("/wishlist", response_model=WishlistSummary)
def get_wishlist(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Get the current user's wishlist."""
    items = crud_shopping.get_user_wishlist(db, current_user.id)
    return WishlistSummary(
        items=items,
        total_items=len(items)
    )


@router.post("/wishlist/toggle/{product_id}")
def toggle_wishlist(product_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Toggle a product in the wishlist (adds if missing, removes if present)."""
    added, message = crud_shopping.toggle_wishlist(db, current_user.id, product_id)
    return {"detail": message, "is_in_wishlist": added}
