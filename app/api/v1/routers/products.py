import csv
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse, CSVImportResponse, CSVImportRowResult
from app.models.user import User
from app.models.product import ConditionEnum
import app.crud.product as crud_product
from app.api.deps import get_db, get_current_verified_seller

router = APIRouter()

from typing import List, Optional

# Expected CSV columns (order matters for the template)
CSV_COLUMNS = [
    "name", "description", "price", "original_price", "image_url", "images",
    "category", "department", "size", "brand", "condition", "tags"
]

VALID_CONDITIONS = {e.value for e in ConditionEnum}


@router.get("/", response_model=List[ProductResponse])
def get_products(
    skip: int = 0, 
    limit: int = 100, 
    category: Optional[str] = None, 
    department: Optional[str] = None, 
    brand: Optional[str] = None,
    q: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort_by: Optional[str] = "newest",
    db: Session = Depends(get_db)
):
    products = crud_product.get_products(
        db, skip=skip, limit=limit, category=category, department=department, 
        brand=brand, q=q, min_price=min_price, max_price=max_price, sort_by=sort_by
    )
    return products

@router.get("/csv-template")
def download_csv_template():
    """
    Download a sample CSV template with the correct column headers and an example row.
    Sellers can fill this out and upload via POST /products/import-csv.
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
        "https://example.com/jacket.jpg",     # image_url
        "https://example.com/img2.jpg|https://example.com/img3.jpg",  # images (pipe-separated)
        "Jackets",                            # category
        "Men",                                # department
        "L",                                  # size
        "Levi's",                             # brand
        "Good",                               # condition (Excellent/Very Good/Good/Fair/Poor)
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
    product = crud_product.get_product(db, product_id=id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.post("/", response_model=ProductResponse)
def create_product(product: ProductCreate, db: Session = Depends(get_db), current_seller: User = Depends(get_current_verified_seller)):
    return crud_product.create_product(
        db=db, 
        product=product, 
        seller_id=current_seller.id,
        is_ai_verified=product.is_ai_verified,
        condition_score=product.condition_score
    )

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
    - 'condition' must be one of: Excellent, Very Good, Good, Fair, Poor
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
        except Exception as e:
            # If bulk insert fails, mark all valid rows as failed
            for product_data in valid_products:
                results.append(CSVImportRowResult(
                    row_number=product_data["_row_num"],
                    success=False,
                    product_name=product_data["name"],
                    error=f"Database error: {str(e)}",
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
def update_product(id: UUID, product_update: ProductUpdate, db: Session = Depends(get_db), current_seller: User = Depends(get_current_verified_seller)):
    product = crud_product.get_product(db, product_id=id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.seller_id != current_seller.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this product")
        
    return crud_product.update_product(db=db, product_id=id, product_update=product_update)

@router.delete("/{id}")
def delete_product(id: UUID, db: Session = Depends(get_db), current_seller: User = Depends(get_current_verified_seller)):
    product = crud_product.get_product(db, product_id=id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.seller_id != current_seller.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this product")
        
    crud_product.delete_product(db=db, product_id=id)
    return {"detail": "Product deleted successfully"}
