"""
Product Router — CRUD endpoints for product management.

Public:  GET /products, GET /products/{id}
Seller:  POST /products, PUT /products/{id}, DELETE /products/{id},
         POST /products/{id}/restore, POST /products/import-csv, GET /products/csv-template
"""
import csv
import io
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.schemas.product import (
    ProductCreate, ProductUpdate, ProductResponse,
    CSVImportResponse, CSVImportRowResult,
)
from app.models.user import User
from app.models.product import ConditionEnum
import app.crud.product as crud_product
from app.api.deps import get_db, get_current_verified_seller, get_current_seller
from app.api.pagination import PageLimit, PageOffset
from app.services.media_lifecycle import MediaAssetValidationError

router = APIRouter()
logger = logging.getLogger(__name__)

# Expected CSV columns (order matters for the template)
CSV_COLUMNS = [
    "name", "description", "price", "original_price", "image_url", "images",
    "category", "department", "size", "brand", "condition", "tags"
]

VALID_CONDITIONS = {e.value for e in ConditionEnum}


@router.get("/", response_model=List[ProductResponse])
def get_products(
    skip: PageOffset = 0,
    limit: PageLimit = 100,
    category_id: Optional[UUID] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    q: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort_by: Optional[str] = "newest",
    seller_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """List non-deleted public products with filtering, search, and sorting."""
    products = crud_product.get_products(
        db,
        skip=skip,
        limit=limit,
        category_id=category_id,
        category_slug=category,
        brand=brand,
        q=q,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
        seller_id=seller_id,
        include_deleted=False,
    )
    return products


@router.get("/seller/me", response_model=List[ProductResponse])
def get_my_products(
    skip: PageOffset = 0,
    limit: PageLimit = 100,
    db: Session = Depends(get_db),
    current_seller: User = Depends(get_current_seller),
):
    """Get products for the currently authenticated seller."""
    return crud_product.get_products(
        db,
        skip=skip,
        limit=limit,
        seller_id=current_seller.id,
        include_deleted=True,
    )

@router.get("/csv-template")
def download_csv_template():
    """
    Download a sample CSV template with the correct column headers and an example row.
    Sellers can fill this out and upload via POST /products/import-csv. Image
    values must be exact URLs returned by POST /upload/image for this seller;
    arbitrary external URLs are rejected.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)
    # Example row
    writer.writerow([
        "Vintage Denim Jacket",              # name
        "Classic 90s style denim jacket",     # description
        "2500",                               # price
        "5000",                               # original_price
        "PASTE_FIRST_UPLOAD_URL_HERE",        # image_url
        "PASTE_SECOND_UPLOAD_URL_HERE|PASTE_THIRD_UPLOAD_URL_HERE",  # images
        "Jackets",                            # category
        "Men",                                # department
        "L",                                  # size
        "Levi's",                             # brand
        "Good",                               # condition
        "vintage|denim|90s",                  # tags (pipe-separated)
    ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=thriftkro_product_template.csv"},
    )


@router.get("/{id}", response_model=ProductResponse)
def get_product(id: UUID, db: Session = Depends(get_db)):
    """Get a non-deleted public product by ID with all relationships."""
    product = crud_product.get_public_product(db, product_id=id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db),
    current_seller: User = Depends(get_current_verified_seller),
):
    """Create a new product listing. Requires verified seller."""
    try:
        return crud_product.create_product(
            db=db,
            product=product,
            seller_id=current_seller.id,
        )
    except MediaAssetValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/import-csv", response_model=CSVImportResponse)
async def import_products_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_seller: User = Depends(get_current_verified_seller),
):
    """
    Bulk import products from a CSV file.

    Expected CSV columns:
    name, description, price, original_price, image_url, images,
    category, department, size, brand, condition, tags

    Notes:
    - 'images' and 'tags' are pipe-separated (|) for multiple values
    - 'condition' must be one of: New, Like New, Excellent, Very Good, Good, Fair, Poor
    - 'price' is required, 'original_price' is optional
    - Maximum 500 rows per import
    """
    # Validate file type
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    # Read file content
    try:
        content = await file.read()
        decoded = content.decode("utf-8-sig")  # utf-8-sig handles BOM from Excel
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read the CSV file. Ensure it is UTF-8 encoded.")

    reader = csv.DictReader(io.StringIO(decoded))

    # Validate headers
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty or has no headers.")

    missing_required = {"name", "price", "image_url", "category", "department", "size", "condition"} - set(reader.fieldnames)
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(sorted(missing_required))}. "
                   f"Download the template from GET /products/csv-template.",
        )

    results: List[CSVImportRowResult] = []
    valid_products = []

    for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is the header
        # Enforce max rows
        if row_num > 501:  # 500 data rows + 1 header
            results.append(CSVImportRowResult(
                row_number=row_num,
                success=False,
                product_name=row.get("name", ""),
                error="Maximum 500 rows per import exceeded.",
            ))
            break

        product_name = row.get("name", "").strip()

        # Validate required fields
        errors = []
        if not product_name:
            errors.append("'name' is required")

        # Parse price
        price = None
        try:
            price = float(row.get("price", "").strip())
            if price <= 0:
                errors.append("'price' must be greater than 0")
        except (ValueError, TypeError):
            errors.append("'price' must be a valid number")

        # Parse original_price (optional)
        original_price = None
        op_str = row.get("original_price", "").strip()
        if op_str:
            try:
                original_price = float(op_str)
            except (ValueError, TypeError):
                errors.append("'original_price' must be a valid number")

        image_url = row.get("image_url", "").strip()
        if not image_url:
            errors.append("'image_url' is required")

        category = row.get("category", "").strip()
        if not category:
            errors.append("'category' is required")

        department = row.get("department", "").strip()
        if not department:
            errors.append("'department' is required")

        size = row.get("size", "").strip()
        if not size:
            errors.append("'size' is required")

        condition_str = row.get("condition", "").strip()
        if not condition_str:
            errors.append("'condition' is required")
        elif condition_str not in VALID_CONDITIONS:
            errors.append(f"'condition' must be one of: {', '.join(sorted(VALID_CONDITIONS))}")

        if errors:
            results.append(CSVImportRowResult(
                row_number=row_num,
                success=False,
                product_name=product_name or None,
                error="; ".join(errors),
            ))
            continue

        # Parse pipe-separated fields
        images_str = row.get("images", "").strip()
        images = [img.strip() for img in images_str.split("|") if img.strip()] if images_str else []

        tags_str = row.get("tags", "").strip()
        tags = [tag.strip() for tag in tags_str.split("|") if tag.strip()] if tags_str else []

        valid_products.append({
            "name": product_name,
            "description": row.get("description", "").strip() or None,
            "price": price,
            "original_price": original_price,
            "image_url": image_url,
            "images": images,
            "category": category,
            "department": department,
            "size": size,
            "brand": row.get("brand", "").strip() or None,
            "condition": condition_str,
            "tags": tags,
            "_row_num": row_num,
        })

    # Bulk insert valid products
    if valid_products:
        try:
            created = crud_product.bulk_create_products(
                db=db,
                products_data=valid_products,
                seller_id=current_seller.id,
            )
            for product_data, db_product in zip(valid_products, created):
                results.append(CSVImportRowResult(
                    row_number=product_data["_row_num"],
                    success=True,
                    product_name=product_data["name"],
                    product_id=db_product.id,
                ))
        except Exception as exc:
            logger.error(
                "CSV product import failed",
                extra={"error_type": type(exc).__name__},
            )
            # If bulk insert fails, mark all valid rows as failed
            for product_data in valid_products:
                results.append(CSVImportRowResult(
                    row_number=product_data["_row_num"],
                    success=False,
                    product_name=product_data["name"],
                    error="Product import could not be completed. No rows were created.",
                ))

    # Sort results by row number
    results.sort(key=lambda r: r.row_number)

    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    return CSVImportResponse(
        total_rows=successful + failed,
        successful=successful,
        failed=failed,
        results=results,
    )


@router.put("/{id}", response_model=ProductResponse)
def update_product(
    id: UUID,
    product_update: ProductUpdate,
    db: Session = Depends(get_db),
    current_seller: User = Depends(get_current_verified_seller),
):
    """Update an existing product. Only the owning seller can update."""
    product = crud_product.get_product(db, product_id=id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.seller_id != current_seller.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this product")

    try:
        return crud_product.update_product(
            db=db,
            product_id=id,
            product_update=product_update,
        )
    except MediaAssetValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{id}")
def delete_product(
    id: UUID,
    db: Session = Depends(get_db),
    current_seller: User = Depends(get_current_verified_seller),
):
    """Soft-delete a product (move to trash). Only the owning seller can delete."""
    product = crud_product.get_product(db, product_id=id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.seller_id != current_seller.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this product")

    crud_product.delete_product(db=db, product_id=id)
    return {"detail": "Product moved to trash successfully"}


@router.post("/{id}/restore")
def restore_product(
    id: UUID,
    db: Session = Depends(get_db),
    current_seller: User = Depends(get_current_verified_seller),
):
    """Restore a soft-deleted product. Only the owning seller can restore."""
    product = crud_product.get_product(db, product_id=id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.seller_id != current_seller.id:
        raise HTTPException(status_code=403, detail="Not authorized to restore this product")

    success = crud_product.restore_product(db=db, product_id=id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to restore product")
    return {"detail": "Product restored successfully"}
