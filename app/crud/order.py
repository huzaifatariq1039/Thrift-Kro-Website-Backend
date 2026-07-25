from sqlalchemy.orm import Session
from app.models.order import Order, OrderStatusEnum
from app.models.product import Product, StatusEnum as ProductStatusEnum
from app.models.user import Wallet
from app.schemas.order import OrderCreate
from uuid import UUID

def create_order(db: Session, order: OrderCreate, buyer_id: UUID):
    # Fetch product to calculate amounts
    product = db.query(Product).filter(Product.id == order.product_id).first()
    if not product or product.status != ProductStatusEnum.AVAILABLE:
        return None
        
    subtotal = product.price
    escrow_fee = subtotal * 0.02
    shipping_fee = 100.0  # Fixed mock shipping fee
    total_amount = subtotal + escrow_fee + shipping_fee
    
    db_order = Order(
        buyer_id=buyer_id,
        seller_id=product.seller_id,
        product_id=order.product_id,
        shipping_address=order.shipping_address,
        subtotal=subtotal,
        escrow_fee=escrow_fee,
        shipping_fee=shipping_fee,
        total_amount=total_amount,
        payment_method=order.payment_method,
        status=OrderStatusEnum.PENDING
    )
    
    # Process payment (mock logic - just moving to escrow)
    # Deduct from buyer wallet if WALLET is selected
    if order.payment_method == "WALLET":
        buyer_wallet = db.query(Wallet).filter(Wallet.user_id == buyer_id).first()
        if buyer_wallet.balance < total_amount:
            return "INSUFFICIENT_FUNDS"
        buyer_wallet.balance -= total_amount
        db.add(buyer_wallet)
        
    db_order.status = OrderStatusEnum.FUNDS_IN_ESCROW
    product.status = ProductStatusEnum.SOLD
    
    db.add(db_order)
    db.add(product)
    db.commit()
    db.refresh(db_order)
    
    return db_order

def get_orders_by_user(db: Session, user_id: UUID, is_seller: bool = False):
    if is_seller:
        return db.query(Order).filter(Order.seller_id == user_id).all()
    return db.query(Order).filter(Order.buyer_id == user_id).all()

def update_order_status(db: Session, order_id: UUID, status: OrderStatusEnum):
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if db_order:
        db_order.status = status
        db.add(db_order)
        db.commit()
        db.refresh(db_order)
    return db_order

def release_escrow(db: Session, order_id: UUID):
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if not db_order or db_order.status != OrderStatusEnum.DELIVERED:
        return None
        
    # Payout is subtotal + shipping (buyer pays shipping, seller handles it) minus platform fee
    payout_amount = db_order.subtotal + db_order.shipping_fee - db_order.escrow_fee
    
    seller_wallet = db.query(Wallet).filter(Wallet.user_id == db_order.seller_id).first()
    seller_wallet.balance += payout_amount
    
    db_order.status = OrderStatusEnum.COMPLETED_PAYOUT
    
    db.add(seller_wallet)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    
    return db_order
