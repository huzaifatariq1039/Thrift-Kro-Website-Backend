"""
CRUD operations for Shopping Cart and Wishlist.
"""
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from uuid import UUID
from typing import List, Optional, Tuple

from app.models.shopping import CartItem, WishlistItem
from app.models.product import Product, StatusEnum


# --- Shopping Cart ---

def add_to_cart(db: Session, user_id: UUID, product_id: UUID) -> Tuple[Optional[CartItem], str]:
    """
    Add a product to the user's cart and mark it as IN_CART.
    Returns (CartItem, error_message). If successful, error_message is None.
    """
    # 1. Check if product exists and is available
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return None, "Product not found"
    
    if product.status != StatusEnum.AVAILABLE:
        return None, f"Product is currently {product.status.value}"
    
    if product.seller_id == user_id:
        return None, "You cannot add your own product to your cart"
    
    # 2. Add to cart
    cart_item = CartItem(user_id=user_id, product_id=product_id)
    db.add(cart_item)
    
    # 3. Update product status
    product.status = StatusEnum.IN_CART
    
    try:
        db.commit()
        db.refresh(cart_item)
        return cart_item, None
    except IntegrityError:
        db.rollback()
        return None, "Product is already in a cart"


def remove_from_cart(db: Session, user_id: UUID, product_id: UUID) -> bool:
    """
    Remove a product from the user's cart and mark it AVAILABLE.
    Returns True if removed, False if not found.
    """
    cart_item = db.query(CartItem).filter(
        CartItem.user_id == user_id, 
        CartItem.product_id == product_id
    ).first()
    
    if not cart_item:
        return False
        
    product = db.query(Product).filter(Product.id == product_id).first()
    if product and product.status == StatusEnum.IN_CART:
        product.status = StatusEnum.AVAILABLE
        
    db.delete(cart_item)
    db.commit()
    return True


def clear_cart(db: Session, user_id: UUID):
    """Remove all items from the user's cart, making them available again."""
    items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
    for item in items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product and product.status == StatusEnum.IN_CART:
            product.status = StatusEnum.AVAILABLE
        db.delete(item)
    db.commit()


def get_user_cart(db: Session, user_id: UUID) -> List[CartItem]:
    """Get all items in the user's cart."""
    return db.query(CartItem).filter(CartItem.user_id == user_id).order_by(CartItem.added_at.desc()).all()


# --- Wishlist ---

def toggle_wishlist(db: Session, user_id: UUID, product_id: UUID) -> Tuple[bool, str]:
    """
    Toggle a product in the user's wishlist.
    Returns (is_in_wishlist, message).
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return False, "Product not found"
        
    existing = db.query(WishlistItem).filter(
        WishlistItem.user_id == user_id,
        WishlistItem.product_id == product_id
    ).first()
    
    if existing:
        db.delete(existing)
        db.commit()
        return False, "Removed from wishlist"
    else:
        new_item = WishlistItem(user_id=user_id, product_id=product_id)
        db.add(new_item)
        db.commit()
        return True, "Added to wishlist"


def get_user_wishlist(db: Session, user_id: UUID) -> List[WishlistItem]:
    """Get all items in the user's wishlist."""
    return db.query(WishlistItem).filter(
        WishlistItem.user_id == user_id
    ).order_by(WishlistItem.added_at.desc()).all()
