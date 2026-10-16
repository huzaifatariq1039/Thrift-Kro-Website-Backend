"""
CRUD operations for Shopping Cart and Wishlist.

Cart uses the CartSession → CartItem → ProductVariant chain.
All writes are atomic with rollback on failure.
"""
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from typing import List, Optional, Tuple

from app.models.shopping import CartSession, CartItem, WishlistItem
from app.models.product import Product, ProductVariant, ProductStatusEnum
from app.models.user import User


# ─── Cart Session Helpers ─────────────────────────────────────────────

def _get_or_create_cart_session(db: Session, user_id: UUID) -> CartSession:
    """Create the user's cart once, then lock it for the current write."""
    statement = (
        pg_insert(CartSession)
        .values(user_id=user_id)
        .on_conflict_do_nothing(index_elements=[CartSession.user_id])
    )
    db.execute(statement)
    return (
        db.query(CartSession)
        .filter(CartSession.user_id == user_id)
        .with_for_update()
        .one()
    )


# ─── Shopping Cart ────────────────────────────────────────────────────

def add_to_cart(
    db: Session, user_id: UUID, product_variant_id: UUID, quantity: int = 1
) -> Tuple[Optional[CartItem], Optional[str]]:
    """
    Add a product variant to the user's cart.
    Returns (CartItem, error_message). If successful, error_message is None.
    """
    try:
        if quantity <= 0:
            return None, "Quantity must be at least 1"

        # Validate variant exists and has stock
        variant = (
            db.query(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .filter(ProductVariant.id == product_variant_id)
            .first()
        )
        if not variant:
            return None, "Product variant not found"
        if not variant.is_active:
            return None, "Product variant is no longer available"

        product = variant.product
        if not product or product.deleted_at is not None:
            return None, "Product is no longer available"

        if product.status != ProductStatusEnum.AVAILABLE:
            return None, f"Product is currently {product.status.value}"

        if product.seller_id == user_id:
            return None, "You cannot add your own product to your cart"

        if variant.quantity_in_stock < quantity:
            return None, f"Only {variant.quantity_in_stock} item(s) in stock"

        # Get or create cart session
        cart_session = _get_or_create_cart_session(db, user_id)

        insert_statement = pg_insert(CartItem).values(
            cart_session_id=cart_session.id,
            product_variant_id=product_variant_id,
            quantity=quantity,
        )
        next_quantity = CartItem.quantity + insert_statement.excluded.quantity
        statement = (
            insert_statement.on_conflict_do_update(
                index_elements=[
                    CartItem.cart_session_id,
                    CartItem.product_variant_id,
                ],
                set_={"quantity": next_quantity},
                where=next_quantity <= variant.quantity_in_stock,
            )
            .returning(CartItem.id)
        )
        cart_item_id = db.execute(statement).scalar_one_or_none()

        if cart_item_id is None:
            existing_quantity = (
                db.query(CartItem.quantity)
                .filter(
                    CartItem.cart_session_id == cart_session.id,
                    CartItem.product_variant_id == product_variant_id,
                )
                .scalar()
            )
            db.rollback()
            return None, (
                f"Cannot add more. Only {variant.quantity_in_stock} in stock, "
                f"you already have {existing_quantity or 0} in cart"
            )

        db.commit()
        return db.get(CartItem, cart_item_id), None

    except Exception:
        db.rollback()
        raise


def remove_from_cart(db: Session, user_id: UUID, cart_item_id: UUID) -> bool:
    """
    Remove a specific item from the user's cart by cart_item_id.
    Returns True if removed, False if not found.
    """
    cart_session = db.query(CartSession).filter(CartSession.user_id == user_id).first()
    if not cart_session:
        return False

    cart_item = db.query(CartItem).filter(
        CartItem.id == cart_item_id,
        CartItem.cart_session_id == cart_session.id,
    ).first()

    if not cart_item:
        return False

    db.delete(cart_item)
    db.commit()
    return True


def remove_variant_from_cart(db: Session, user_id: UUID, product_variant_id: UUID) -> bool:
    """
    Remove an item from the user's cart by product_variant_id.
    Returns True if removed, False if not found.
    """
    cart_session = db.query(CartSession).filter(CartSession.user_id == user_id).first()
    if not cart_session:
        return False

    cart_item = db.query(CartItem).filter(
        CartItem.cart_session_id == cart_session.id,
        CartItem.product_variant_id == product_variant_id,
    ).first()

    if not cart_item:
        return False

    db.delete(cart_item)
    db.commit()
    return True


def update_cart_item_quantity(db: Session, user_id: UUID, cart_item_id: UUID, quantity: int) -> Tuple[Optional[CartItem], Optional[str]]:
    """Update the quantity of a cart item."""
    cart_session = db.query(CartSession).filter(CartSession.user_id == user_id).first()
    if not cart_session:
        return None, "Cart not found"

    cart_item = (
        db.query(CartItem)
        .options(joinedload(CartItem.product_variant))
        .filter(
            CartItem.id == cart_item_id,
            CartItem.cart_session_id == cart_session.id,
        )
        .first()
    )

    if not cart_item:
        return None, "Cart item not found"

    if quantity <= 0:
        db.delete(cart_item)
        db.commit()
        return None, None  # Removed

    if quantity > cart_item.product_variant.quantity_in_stock:
        return None, f"Only {cart_item.product_variant.quantity_in_stock} in stock"

    cart_item.quantity = quantity
    db.commit()
    db.refresh(cart_item)
    return cart_item, None


def clear_cart(db: Session, user_id: UUID):
    """Remove all items from the user's cart."""
    cart_session = db.query(CartSession).filter(CartSession.user_id == user_id).first()
    if cart_session:
        db.query(CartItem).filter(CartItem.cart_session_id == cart_session.id).delete()
        db.commit()


def get_user_cart(db: Session, user_id: UUID) -> List[CartItem]:
    """Get all items in the user's cart with product details."""
    cart_session = db.query(CartSession).filter(CartSession.user_id == user_id).first()
    if not cart_session:
        return []

    return (
        db.query(CartItem)
        .options(
            joinedload(CartItem.product_variant).joinedload(ProductVariant.product).joinedload(Product.images),
            joinedload(CartItem.product_variant).joinedload(ProductVariant.product).joinedload(Product.seller),
        )
        .filter(CartItem.cart_session_id == cart_session.id)
        .order_by(CartItem.added_at.desc())
        .all()
    )


def get_cart_session(db: Session, user_id: UUID) -> Optional[CartSession]:
    """Get the cart session for a user."""
    return db.query(CartSession).filter(CartSession.user_id == user_id).first()


# ─── Wishlist ─────────────────────────────────────────────────────────

def toggle_wishlist(db: Session, user_id: UUID, product_id: UUID) -> Tuple[bool, str]:
    """
    Toggle a product in the user's wishlist.
    Returns (is_in_wishlist, message).
    """
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return False, "Product not found"

        # A toggle is a read-modify-write operation. Locking the owner makes two
        # concurrent toggles equivalent to two deterministic sequential toggles,
        # including when the wishlist row does not exist yet.
        (
            db.query(User.id)
            .filter(User.id == user_id)
            .with_for_update()
            .one()
        )
        existing = db.query(WishlistItem).filter(
            WishlistItem.user_id == user_id,
            WishlistItem.product_id == product_id,
        ).first()

        if existing:
            db.delete(existing)
            db.commit()
            return False, "Removed from wishlist"

        db.add(WishlistItem(user_id=user_id, product_id=product_id))
        db.commit()
        return True, "Added to wishlist"
    except Exception:
        db.rollback()
        raise


def get_user_wishlist(db: Session, user_id: UUID) -> List[WishlistItem]:
    """Get all items in the user's wishlist."""
    return (
        db.query(WishlistItem)
        .options(
            joinedload(WishlistItem.product).joinedload(Product.images),
            joinedload(WishlistItem.product).joinedload(Product.seller),
        )
        .filter(WishlistItem.user_id == user_id)
        .order_by(WishlistItem.added_at.desc())
        .all()
    )
