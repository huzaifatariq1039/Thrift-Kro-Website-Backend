"""
CRUD operations for Categories.
"""
import re
from sqlalchemy.orm import Session, with_loader_criteria
from app.models.product import Category
from app.schemas.category import CategoryCreate, CategoryUpdate
from uuid import UUID
from typing import Optional, List


def _active_tree_options():
    """Keep inactive descendants out of public category response trees."""
    return with_loader_criteria(
        Category,
        lambda category: category.is_active.is_(True),
        include_aliases=True,
    )


def _generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from a category name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _ensure_unique_slug(db: Session, slug: str, exclude_id: UUID = None) -> str:
    """Ensure the slug is unique. Append a number suffix if needed."""
    base_slug = slug
    counter = 1
    while True:
        query = db.query(Category).filter(Category.slug == slug)
        if exclude_id:
            query = query.filter(Category.id != exclude_id)
        if not query.first():
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


def get_categories(
    db: Session,
    include_inactive: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> List[Category]:
    """Get a bounded page of top-level categories with their subcategories."""
    query = db.query(Category).filter(Category.parent_id == None)  # noqa: E711
    if not include_inactive:
        query = query.options(_active_tree_options()).filter(Category.is_active.is_(True))
    return query.order_by(Category.name.asc(), Category.id.asc()).offset(skip).limit(limit).all()


def get_all_categories(
    db: Session,
    include_inactive: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> List[Category]:
    """Get a bounded page of categories as a flat list."""
    query = db.query(Category)
    if not include_inactive:
        query = query.options(_active_tree_options()).filter(Category.is_active.is_(True))
    return query.order_by(Category.name.asc(), Category.id.asc()).offset(skip).limit(limit).all()


def get_category(db: Session, category_id: UUID) -> Optional[Category]:
    return db.query(Category).filter(Category.id == category_id).first()


def get_category_by_slug(db: Session, slug: str) -> Optional[Category]:
    return db.query(Category).filter(Category.slug == slug).first()


def get_active_category(db: Session, category_id: UUID) -> Optional[Category]:
    """Get an active category and only active descendants for public use."""
    return (
        db.query(Category)
        .options(_active_tree_options())
        .filter(Category.id == category_id, Category.is_active.is_(True))
        .first()
    )


def get_active_category_by_slug(db: Session, slug: str) -> Optional[Category]:
    """Get an active category by slug for public use."""
    return (
        db.query(Category)
        .options(_active_tree_options())
        .filter(Category.slug == slug, Category.is_active.is_(True))
        .first()
    )


def create_category(db: Session, data: CategoryCreate) -> Category:
    """Create a new category with auto-generated slug."""
    slug = _generate_slug(data.name)
    slug = _ensure_unique_slug(db, slug)

    category = Category(
        name=data.name,
        slug=slug,
        description=data.description,
        image_url=data.image_url,
        parent_id=data.parent_id,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def update_category(db: Session, category_id: UUID, data: CategoryUpdate) -> Optional[Category]:
    """Update a category. Regenerates slug if name changes."""
    category = get_category(db, category_id)
    if not category:
        return None

    update_data = data.model_dump(exclude_unset=True)

    if "name" in update_data:
        slug = _generate_slug(update_data["name"])
        slug = _ensure_unique_slug(db, slug, exclude_id=category_id)
        category.slug = slug

    for key, value in update_data.items():
        setattr(category, key, value)

    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, category_id: UUID) -> bool:
    """Soft-delete a category by setting is_active=False."""
    category = get_category(db, category_id)
    if not category:
        return False
    category.is_active = False
    db.commit()
    return True
