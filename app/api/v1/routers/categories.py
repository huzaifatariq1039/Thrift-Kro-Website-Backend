"""
Category Router — public listing + admin management.

Public:  GET /categories, GET /categories/{id}
Admin:   POST /categories, PUT /categories/{id}, DELETE /categories/{id}
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from app.models.user import User
from app.api.deps import get_db, get_current_admin
import app.crud.category as crud_category

router = APIRouter()


@router.get("/", response_model=List[CategoryResponse])
def list_categories(
    flat: bool = False,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    """
    List categories. By default returns top-level categories with nested subcategories.
    Set flat=true for a flat list of all categories.
    """
    if flat:
        return crud_category.get_all_categories(db, include_inactive=include_inactive)
    return crud_category.get_categories(db, include_inactive=include_inactive)


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: UUID, db: Session = Depends(get_db)):
    """Get a single category by ID with its subcategories."""
    category = crud_category.get_category(db, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.get("/slug/{slug}", response_model=CategoryResponse)
def get_category_by_slug(slug: str, db: Session = Depends(get_db)):
    """Get a category by its URL slug."""
    category = crud_category.get_category_by_slug(db, slug)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Admin: Create a new category."""
    return crud_category.create_category(db, data)


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Admin: Update a category."""
    category = crud_category.update_category(db, category_id, data)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.delete("/{category_id}")
def delete_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Admin: Soft-delete a category (set is_active=False)."""
    success = crud_category.delete_category(db, category_id)
    if not success:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"detail": "Category deactivated"}
