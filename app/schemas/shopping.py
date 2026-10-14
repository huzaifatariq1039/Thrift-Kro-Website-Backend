"""Shopping Cart and Wishlist schemas."""
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from datetime import datetime


# ─── Cart Schemas ─────────────────────────────────────────────────────

class AddToCartRequest(BaseModel):
    product_variant_id: UUID
    quantity: int = Field(1, ge=1, le=100)


class UpdateCartItemRequest(BaseModel):
    quantity: int = Field(..., ge=0, le=100)


class CartItemProductInfo(BaseModel):
    """Minimal product info embedded in cart items."""
    id: UUID
    name: str
    price: float
    brand: Optional[str] = None
    primary_image_url: Optional[str] = None
    seller_name: Optional[str] = None

    class Config:
        from_attributes = True


class CartItemVariantInfo(BaseModel):
    """Variant info embedded in cart items."""
    id: UUID
    sku: Optional[str] = None
    attributes: dict = {}
    price_adjustment: float = 0.0
    quantity_in_stock: int = 1

    class Config:
        from_attributes = True


class CartItemResponse(BaseModel):
    id: UUID
    product_variant_id: UUID
    quantity: int
    added_at: datetime

    # Computed nested data
    variant: Optional[CartItemVariantInfo] = None
    product: Optional[CartItemProductInfo] = None
    line_total: float = 0.0

    class Config:
        from_attributes = True

    @classmethod
    def from_cart_item(cls, item) -> "CartItemResponse":
        """Build response from a CartItem ORM object with eager-loaded relationships."""
        variant = item.product_variant
        product = variant.product if variant else None

        variant_info = None
        product_info = None
        line_total = 0.0

        if variant:
            variant_info = CartItemVariantInfo(
                id=variant.id,
                sku=variant.sku,
                attributes=variant.attributes or {},
                price_adjustment=variant.price_adjustment,
                quantity_in_stock=variant.quantity_in_stock,
            )

        if product:
            # Get primary image
            primary_image = None
            if product.images:
                primary = next((img for img in product.images if img.is_primary), None)
                primary_image = primary.image_url if primary else product.images[0].image_url

            # Get seller name
            seller_name = None
            if product.seller:
                if hasattr(product.seller, "seller_profile") and product.seller.seller_profile:
                    seller_name = product.seller.seller_profile.shop_name
                else:
                    seller_name = product.seller.full_name

            product_info = CartItemProductInfo(
                id=product.id,
                name=product.name,
                price=product.price,
                brand=product.brand,
                primary_image_url=primary_image,
                seller_name=seller_name,
            )

            unit_price = product.price + (variant.price_adjustment if variant else 0)
            line_total = unit_price * item.quantity

        return cls(
            id=item.id,
            product_variant_id=item.product_variant_id,
            quantity=item.quantity,
            added_at=item.added_at,
            variant=variant_info,
            product=product_info,
            line_total=line_total,
        )


class CartSummary(BaseModel):
    items: List[CartItemResponse]
    total_price: float
    total_items: int


# ─── Wishlist Schemas ─────────────────────────────────────────────────

class WishlistProductInfo(BaseModel):
    id: UUID
    name: str
    price: float
    brand: Optional[str] = None
    primary_image_url: Optional[str] = None

    class Config:
        from_attributes = True


class WishlistItemResponse(BaseModel):
    id: UUID
    user_id: UUID
    product_id: UUID
    added_at: datetime
    product: Optional[WishlistProductInfo] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_wishlist_item(cls, item) -> "WishlistItemResponse":
        product_info = None
        if item.product:
            primary_image = None
            if hasattr(item.product, "images") and item.product.images:
                primary = next((img for img in item.product.images if img.is_primary), None)
                primary_image = primary.image_url if primary else item.product.images[0].image_url

            product_info = WishlistProductInfo(
                id=item.product.id,
                name=item.product.name,
                price=item.product.price,
                brand=item.product.brand,
                primary_image_url=primary_image,
            )

        return cls(
            id=item.id,
            user_id=item.user_id,
            product_id=item.product_id,
            added_at=item.added_at,
            product=product_info,
        )


class WishlistSummary(BaseModel):
    items: List[WishlistItemResponse]
    total_items: int


# ─── Checkout ─────────────────────────────────────────────────────────

class CartCheckoutRequest(BaseModel):
    shipping_address_id: Optional[UUID] = None
    payment_method: str = "CASH_ON_DELIVERY"
