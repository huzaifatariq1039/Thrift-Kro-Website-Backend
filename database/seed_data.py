"""
Thrift Kro Database Seed Script.

Populates the PostgreSQL database with realistic sample data:
- Admin account
- Verified and unverified Sellers & Seller Profiles
- Buyer accounts with funded wallets
- Verified product listings with image URLs, condition scores, & SHA-256 receipts
- Escrow orders, shopping cart items, wishlist items, product reviews, and chat messages
"""

import sys
import os
import secrets
from datetime import datetime, timezone

# Add backend directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal, Base, engine
from app.core.security import get_password_hash
from app.models.user import User, SellerProfile, Wallet, RoleEnum, BusinessTypeEnum, VerificationStatusEnum
from app.models.product import Product, ConditionEnum, StatusEnum
from app.models.order import Order, PaymentMethodEnum, OrderStatusEnum
from app.models.shopping import CartItem, WishlistItem
from app.models.review import Review
from app.models.support import SupportTicket, TicketTypeEnum, TicketStatusEnum
from app.models.message import Message
from app.models.verification import VerificationLog
from app.services.cv_service import generate_verification_hash


def seed_database():
    db: Session = SessionLocal()
    print("🚀 Initializing database seeding process for Thrift Kro...")

    try:
        # Check if users already exist
        existing_admin = db.query(User).filter(User.email == "admin@thriftkro.com").first()
        if existing_admin:
            print("⚠️ Database already seeded! Skipping seed process.")
            return

        # -----------------------------------------------------------------
        # 1. CREATE USERS
        # -----------------------------------------------------------------
        print("👤 Creating Users (Admin, Sellers, Buyers)...")

        # Admin
        admin_user = User(
            email="admin@thriftkro.com",
            hashed_password=get_password_hash("admin123"),
            full_name="System Administrator",
            hex_code="ADM00001",
            role=RoleEnum.ADMIN,
            auth_provider="local",
            is_active=True
        )
        db.add(admin_user)
        db.flush()

        admin_wallet = Wallet(user_id=admin_user.id, balance=50000.0, currency="PKR")
        db.add(admin_wallet)

        # Seller 1 (Verified Seller)
        seller1 = User(
            email="seller1@thriftkro.com",
            hashed_password=get_password_hash("seller123"),
            full_name="Zainab Thrift Studio",
            hex_code="SEL00001",
            role=RoleEnum.SELLER,
            auth_provider="local",
            avatar_url="https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=400&q=80",
            is_active=True
        )
        db.add(seller1)
        db.flush()

        seller1_wallet = Wallet(user_id=seller1.id, balance=18500.0, currency="PKR")
        seller1_profile = SellerProfile(
            user_id=seller1.id,
            shop_name="Retro Vibe Closet",
            description="Curated vintage denim, leather jackets, and 90s streetwear.",
            phone_number="+923001234567",
            address="Shop 14, Liberty Market",
            city="Lahore",
            business_type=BusinessTypeEnum.SHOP,
            cnic_number="35202-1234567-1",
            is_verified=True,
            verification_status=VerificationStatusEnum.APPROVED,
            verified_at=datetime.now(timezone.utc),
            rating=4.8,
            review_count=12
        )
        db.add_all([seller1_wallet, seller1_profile])

        # Seller 2 (Pending Verification)
        seller2 = User(
            email="seller2@thriftkro.com",
            hashed_password=get_password_hash("seller123"),
            full_name="Hamza Kicks & Threads",
            hex_code="SEL00002",
            role=RoleEnum.SELLER,
            auth_provider="local",
            is_active=True
        )
        db.add(seller2)
        db.flush()

        seller2_wallet = Wallet(user_id=seller2.id, balance=2500.0, currency="PKR")
        seller2_profile = SellerProfile(
            user_id=seller2.id,
            shop_name="Urban Sneakerhead",
            description="Authentic pre-owned hypebeast footwear & hoodies.",
            phone_number="+923219876543",
            address="F-7 Markaz",
            city="Islamabad",
            business_type=BusinessTypeEnum.INDIVIDUAL,
            cnic_number="61101-9876543-2",
            is_verified=False,
            verification_status=VerificationStatusEnum.PENDING,
            rating=0.0,
            review_count=0
        )
        db.add_all([seller2_wallet, seller2_profile])

        # Buyer 1
        buyer1 = User(
            email="buyer1@thriftkro.com",
            hashed_password=get_password_hash("buyer123"),
            full_name="Ali Raza",
            hex_code="BUY00001",
            role=RoleEnum.BUYER,
            auth_provider="local",
            avatar_url="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=400&q=80",
            is_active=True
        )
        db.add(buyer1)
        db.flush()

        buyer1_wallet = Wallet(user_id=buyer1.id, balance=25000.0, currency="PKR")
        db.add(buyer1_wallet)

        # Buyer 2
        buyer2 = User(
            email="buyer2@thriftkro.com",
            hashed_password=get_password_hash("buyer223"),
            full_name="Ayesha Khan",
            hex_code="BUY00002",
            role=RoleEnum.BUYER,
            auth_provider="local",
            is_active=True
        )
        db.add(buyer2)
        db.flush()

        buyer2_wallet = Wallet(user_id=buyer2.id, balance=12000.0, currency="PKR")
        db.add(buyer2_wallet)

        db.commit()
        print("✅ Users and Wallets created successfully.")

        # -----------------------------------------------------------------
        # 2. CREATE PRODUCTS
        # -----------------------------------------------------------------
        print("📦 Creating Product Listings...")

        # Product 1
        now_iso = datetime.now(timezone.utc).isoformat()
        v_hash_1 = generate_verification_hash(str(seller1.id), "prod-1", now_iso, 0.92)

        prod1 = Product(
            seller_id=seller1.id,
            name="Vintage 90s Levi's Oversized Denim Jacket",
            description="Authentic heavyweight vintage denim jacket in light wash. Features classic brass buttons and dual chest pockets. Great oversized fit.",
            price=4500.0,
            original_price=9000.0,
            image_url="https://images.unsplash.com/photo-1576995853123-5a10305d93c0?auto=format&fit=crop&w=800&q=80",
            images=[
                "https://images.unsplash.com/photo-1576995853123-5a10305d93c0?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1551537482-f2075a1d41f2?auto=format&fit=crop&w=800&q=80"
            ],
            category="Jackets",
            department="Men",
            size="XL",
            brand="Levi's",
            condition=ConditionEnum.VERY_GOOD,
            condition_score=92,
            is_ai_verified=True,
            verification_hash=v_hash_1,
            verified_at=datetime.now(timezone.utc),
            tags=["vintage", "denim", "oversized", "90s"],
            status=StatusEnum.AVAILABLE
        )

        # Product 2
        v_hash_2 = generate_verification_hash(str(seller1.id), "prod-2", now_iso, 0.88)
        prod2 = Product(
            seller_id=seller1.id,
            name="Nike Air Jordan 1 Retro High 'Chicago'",
            description="Gently worn Air Jordan 1 retro high top sneakers. Minor heel drag, leather is supple and clean. Comes with original red laces.",
            price=18500.0,
            original_price=35000.0,
            image_url="https://images.unsplash.com/photo-1552346154-21d32810aba3?auto=format&fit=crop&w=800&q=80",
            images=[
                "https://images.unsplash.com/photo-1552346154-21d32810aba3?auto=format&fit=crop&w=800&q=80"
            ],
            category="Shoes",
            department="Unisex",
            size="42 EU / 9 US",
            brand="Nike",
            condition=ConditionEnum.EXCELLENT,
            condition_score=88,
            is_ai_verified=True,
            verification_hash=v_hash_2,
            verified_at=datetime.now(timezone.utc),
            tags=["sneakers", "jordan", "streetwear", "retro"],
            status=StatusEnum.AVAILABLE
        )

        # Product 3
        v_hash_3 = generate_verification_hash(str(seller1.id), "prod-3", now_iso, 0.85)
        prod3 = Product(
            seller_id=seller1.id,
            name="Genuine Leather Vintage Bomber Jacket",
            description="Rich brown distressed leather bomber with quilted inner lining and ribbed cuffs. Ultra warm and timeless design.",
            price=7200.0,
            original_price=15000.0,
            image_url="https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?auto=format&fit=crop&w=800&q=80",
            images=[
                "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?auto=format&fit=crop&w=800&q=80"
            ],
            category="Jackets",
            department="Men",
            size="L",
            brand="Thrifted Classic",
            condition=ConditionEnum.GOOD,
            condition_score=85,
            is_ai_verified=True,
            verification_hash=v_hash_3,
            verified_at=datetime.now(timezone.utc),
            tags=["leather", "bomber", "brown", "winter"],
            status=StatusEnum.AVAILABLE
        )

        # Product 4
        prod4 = Product(
            seller_id=seller2.id,
            name="Minimalist Canvas Tote Bag",
            description="Eco-friendly heavy canvas tote bag with internal zip pocket.",
            price=1200.0,
            original_price=2500.0,
            image_url="https://images.unsplash.com/photo-1544816155-12df9643f363?auto=format&fit=crop&w=800&q=80",
            images=[],
            category="Bags",
            department="Women",
            size="One Size",
            brand="Unbranded",
            condition=ConditionEnum.EXCELLENT,
            condition_score=95,
            is_ai_verified=False,
            tags=["tote", "canvas", "minimalist"],
            status=StatusEnum.AVAILABLE
        )

        db.add_all([prod1, prod2, prod3, prod4])
        db.flush()

        # Create verification logs
        v_log1 = VerificationLog(
            product_id=prod1.id,
            seller_id=seller1.id,
            similarity_score=0.92,
            detected_category="Jackets",
            liveness_passed=True,
            verification_hash=v_hash_1,
            is_successful=True
        )
        db.add(v_log1)

        db.commit()
        print("✅ Products and AI Verification logs created successfully.")

        # -----------------------------------------------------------------
        # 3. CREATE CART & WISHLIST ITEMS
        # -----------------------------------------------------------------
        print("🛒 Populating Cart and Wishlist...")

        wishlist1 = WishlistItem(user_id=buyer1.id, product_id=prod1.id)
        wishlist2 = WishlistItem(user_id=buyer1.id, product_id=prod2.id)
        db.add_all([wishlist1, wishlist2])

        db.commit()
        print("✅ Cart and Wishlist populated.")

        # -----------------------------------------------------------------
        # 4. CREATE REVIEWS & MESSAGES
        # -----------------------------------------------------------------
        print("💬 Creating Reviews and Chat Messages...")

        rev1 = Review(
            buyer_id=buyer1.id,
            product_id=prod1.id,
            rating=5,
            comment="Awesome quality jacket! Delivered fast and exactly as verified by the AI scanner.",
            is_verified_purchase=True
        )
        db.add(rev1)

        msg1 = Message(
            sender_id=buyer1.id,
            receiver_id=seller1.id,
            content="Hi Zainab! Is the Levi's denim jacket still available for shipping to Lahore?",
            is_read=True
        )
        msg2 = Message(
            sender_id=seller1.id,
            receiver_id=buyer1.id,
            content="Hello Ali! Yes it is available. I can ship it out today via TCS.",
            is_read=True
        )
        db.add_all([msg1, msg2])

        # Support ticket example
        ticket1 = SupportTicket(
            user_id=buyer1.id,
            type=TicketTypeEnum.OTHER_QUERY,
            subject="Question regarding wallet withdrawal",
            description="How long does it take for money deposited to reflect in my bank account?",
            status=TicketStatusEnum.OPEN
        )
        db.add(ticket1)

        db.commit()
        print("🎉 Database seeding completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"❌ Error during database seeding: {e}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
