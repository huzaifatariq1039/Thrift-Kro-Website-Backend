from sqlalchemy.orm import Session
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate
from uuid import UUID

def get_product(db: Session, product_id: UUID):
    return db.query(Product).filter(Product.id == product_id).first()

def get_products(
    db: Session, 
    skip: int = 0, 
    limit: int = 100, 
    category: str = None, 
    department: str = None, 
    brand: str = None,
    q: str = None,
    min_price: float = None,
    max_price: float = None,
    sort_by: str = "newest"
):
    from sqlalchemy import or_
    
    query = db.query(Product)
    
    # Text search
    if q:
        search_term = f"%{q}%"
        query = query.filter(
            or_(
                Product.name.ilike(search_term),
                Product.description.ilike(search_term),
                Product.brand.ilike(search_term)
            )
        )
        
    # Filters
    if category:
        query = query.filter(Product.category == category)
    if department:
        query = query.filter(Product.department == department)
    if brand:
        query = query.filter(Product.brand == brand)
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
        
    # Sorting
    if sort_by == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort_by == "price_desc":
        query = query.order_by(Product.price.desc())
    else:  # newest
        # UUIDv4 isn't strictly sortable by time, but in a real app we'd add created_at
        # Assuming we might add created_at later, for now we just order by ID or fall back to default
        query = query.order_by(Product.id.desc())
        
    return query.offset(skip).limit(limit).all()

def create_product(db: Session, product: ProductCreate, seller_id: UUID, is_ai_verified: bool = False, condition_score: int = None):
    db_product = Product(
        **product.model_dump(),
        seller_id=seller_id,
        is_ai_verified=is_ai_verified,
        condition_score=condition_score
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

def bulk_create_products(db: Session, products_data: list, seller_id: UUID) -> list:
    """Create multiple products in a single transaction. Returns list of created Product objects."""
    created = []
    for data in products_data:
        db_product = Product(
            seller_id=seller_id,
            name=data["name"],
            description=data.get("description"),
            price=data["price"],
            original_price=data.get("original_price"),
            image_url=data["image_url"],
            images=data.get("images", []),
            category=data["category"],
            department=data["department"],
            size=data["size"],
            brand=data.get("brand"),
            condition=data["condition"],
            tags=data.get("tags", []),
        )
        db.add(db_product)
        created.append(db_product)
    db.commit()
    for p in created:
        db.refresh(p)
    return created

def update_product(db: Session, product_id: UUID, product_update: ProductUpdate):
    db_product = get_product(db, product_id)
    if not db_product:
        return None
    
    update_data = product_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_product, key, value)
        
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

def delete_product(db: Session, product_id: UUID):
    db_product = get_product(db, product_id)
    if db_product:
        db.delete(db_product)
        db.commit()
    return db_product

def mark_product_verified(db: Session, product_id: UUID, verification_hash: str, similarity_score: float = None):
    """Mark a product as AI-verified with cryptographic proof."""
    from datetime import datetime, timezone
    
    db_product = get_product(db, product_id)
    if not db_product:
        return None
    
    db_product.is_ai_verified = True
    db_product.verification_hash = verification_hash
    db_product.verified_at = datetime.now(timezone.utc)
    if similarity_score is not None:
        db_product.condition_score = int(similarity_score * 100)
    
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

