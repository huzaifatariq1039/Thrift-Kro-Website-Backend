"""
CRUD operations for Products, with proper relational model handling.

All write operations use atomic transactions with rollback on failure.
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from app.models.product import Product, ProductImage, ProductVariant, ProductTag, Category
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.product_variants import reconcile_product_variants
from uuid import UUID
from typing import Optional, List


def get_product(db: Session, product_id: UUID) -> Optional[Product]:
    """Get a single product with all relationships eagerly loaded."""
    return (
        db.query(Product)
        .options(
            joinedload(Product.images),
            joinedload(Product.variants),
            joinedload(Product.tags),
            joinedload(Product.category),
            joinedload(Product.seller),
        )
        .filter(Product.id == product_id)
        .first()
    )


def get_products(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    category_id: UUID = None,
    category_slug: str = None,
    brand: str = None,
    q: str = None,
    min_price: float = None,
    max_price: float = None,
    sort_by: str = "newest",
    seller_id: UUID = None,
    include_deleted: bool = False,
) -> List[Product]:
    """Query products with filtering, search, and sorting."""
    query = db.query(Product).options(
        joinedload(Product.images),
        joinedload(Product.variants),
        joinedload(Product.tags),
        joinedload(Product.category),
        joinedload(Product.seller),
    )

    if not include_deleted:
        query = query.filter(Product.deleted_at == None)  # noqa: E711

    # Text search across name, description, brand
    if q:
        search_term = f"%{q}%"
        query = query.filter(
            or_(
                Product.name.ilike(search_term),
                Product.description.ilike(search_term),
                Product.brand.ilike(search_term),
            )
        )

    # Filters
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if category_slug:
        query = query.join(Category).filter(Category.slug == category_slug)
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    if seller_id:
        query = query.filter(Product.seller_id == seller_id)

    # Sorting
    if sort_by == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort_by == "price_desc":
        query = query.order_by(Product.price.desc())
    elif sort_by == "oldest":
        query = query.order_by(Product.created_at.asc())
    else:  # newest (default)
        query = query.order_by(Product.created_at.desc())

    return query.offset(skip).limit(limit).all()


def create_product(
    db: Session,
    product: ProductCreate,
    seller_id: UUID,
) -> Product:
    """
    Create a product with its related images, variants, and tags
    in a single atomic transaction.
    """
    try:
        # Create the product
        db_product = Product(
            seller_id=seller_id,
            category_id=product.category_id,
            name=product.name,
            description=product.description,
            price=product.price,
            original_price=product.original_price,
            brand=product.brand,
            condition=product.condition,
            is_ai_verified=False,
            verification_hash=None,
        )
        db.add(db_product)
        db.flush()  # Get the product ID without committing

        # Create images
        for img_data in product.images:
            db_image = ProductImage(
                product_id=db_product.id,
                image_url=img_data.image_url,
                is_primary=img_data.is_primary,
                display_order=img_data.display_order,
            )
            db.add(db_image)

        # Create variants (at least one default variant)
        for variant_data in product.variants:
            db_variant = ProductVariant(
                product_id=db_product.id,
                sku=variant_data.sku,
                attributes=variant_data.attributes,
                price_adjustment=variant_data.price_adjustment,
                quantity_in_stock=variant_data.quantity_in_stock,
            )
            db.add(db_variant)

        # Create tags
        for tag_name in product.tags:
            db_tag = ProductTag(
                product_id=db_product.id,
                tag_name=tag_name.strip(),
            )
            db.add(db_tag)

        db.commit()
        db.refresh(db_product)
        return get_product(db, db_product.id)
    except Exception:
        db.rollback()
        raise


def bulk_create_products(db: Session, products_data: list, seller_id: UUID) -> list:
    """
    Create multiple products in a single transaction.
    Each product dict should have: name, description, price, original_price,
    category_name, brand, condition, images (list of URLs), tags (list of strings).
    Returns list of created Product objects.
    """
    created = []
    try:
        for data in products_data:
            # Look up or create category by name
            category_id = None
            category_name = data.get("category", "").strip()
            if category_name:
                category = db.query(Category).filter(
                    Category.name.ilike(category_name)
                ).first()
                if category:
                    category_id = category.id

            db_product = Product(
                seller_id=seller_id,
                category_id=category_id,
                name=data["name"],
                description=data.get("description"),
                price=data["price"],
                original_price=data.get("original_price"),
                brand=data.get("brand"),
                condition=data.get("condition", "New"),
            )
            db.add(db_product)
            db.flush()

            # Create primary image from image_url
            image_url = data.get("image_url", "")
            if image_url:
                db.add(ProductImage(
                    product_id=db_product.id,
                    image_url=image_url,
                    is_primary=True,
                    display_order=0,
                ))

            # Create additional images
            for idx, img_url in enumerate(data.get("images", []), start=1):
                if img_url.strip():
                    db.add(ProductImage(
                        product_id=db_product.id,
                        image_url=img_url.strip(),
                        is_primary=False,
                        display_order=idx,
                    ))

            # Create a default variant with size from CSV
            size = data.get("size", "")
            attributes = {}
            if size:
                attributes["size"] = size
            department = data.get("department", "")
            if department:
                attributes["department"] = department

            db.add(ProductVariant(
                product_id=db_product.id,
                attributes=attributes,
                quantity_in_stock=1,
            ))

            # Create tags
            for tag_name in data.get("tags", []):
                if tag_name.strip():
                    db.add(ProductTag(
                        product_id=db_product.id,
                        tag_name=tag_name.strip(),
                    ))

            created.append(db_product)

        db.commit()
        for p in created:
            db.refresh(p)
        return created
    except Exception:
        db.rollback()
        raise


def update_product(db: Session, product_id: UUID, product_update: ProductUpdate) -> Optional[Product]:
    """Update a product and optionally replace its images, variants, or tags."""
    try:
        db_product = db.query(Product).filter(Product.id == product_id).first()
        if not db_product:
            return None

        update_data = product_update.model_dump(exclude_unset=True)

        # Handle images replacement
        images_data = update_data.pop("images", None)
        if images_data is not None:
            # Delete existing images and replace
            db.query(ProductImage).filter(ProductImage.product_id == product_id).delete()
            for img_data in images_data:
                db.add(ProductImage(
                    product_id=product_id,
                    image_url=img_data["image_url"],
                    is_primary=img_data.get("is_primary", False),
                    display_order=img_data.get("display_order", 0),
                ))

        # Handle variants replacement
        variants_data = update_data.pop("variants", None)
        if variants_data is not None:
            reconcile_product_variants(db, product_id, variants_data)

        # Handle tags replacement
        tags_data = update_data.pop("tags", None)
        if tags_data is not None:
            db.query(ProductTag).filter(ProductTag.product_id == product_id).delete()
            for tag_name in tags_data:
                if tag_name.strip():
                    db.add(ProductTag(
                        product_id=product_id,
                        tag_name=tag_name.strip(),
                    ))

        # Update scalar fields
        for key, value in update_data.items():
            setattr(db_product, key, value)

        db.commit()
        return get_product(db, product_id)
    except Exception:
        db.rollback()
        raise


def delete_product(db: Session, product_id: UUID) -> bool:
    """Soft-delete a product by setting deleted_at timestamp."""
    from datetime import datetime, timezone

    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        return False
    db_product.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return True


def restore_product(db: Session, product_id: UUID) -> bool:
    """Restore a soft-deleted product."""
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        return False
    db_product.deleted_at = None
    db.commit()
    return True


def mark_product_verified(
    db: Session,
    product_id: UUID,
    verification_hash: str,
    similarity_score: float = None,
) -> Optional[Product]:
    """Mark a product as AI-verified with cryptographic proof."""
    from datetime import datetime, timezone

    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        return None

    db_product.is_ai_verified = True
    db_product.verification_hash = verification_hash

    db.commit()
    return get_product(db, product_id)


def get_seller_products(db: Session, seller_id: UUID, include_deleted: bool = False) -> List[Product]:
    """Get all products for a specific seller."""
    return get_products(db, seller_id=seller_id, include_deleted=include_deleted, limit=1000)
