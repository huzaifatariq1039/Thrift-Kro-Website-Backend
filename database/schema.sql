-- =====================================================================
-- THRIFT KRO E-COMMERCE MARKETPLACE - OPTIMIZED POSTGRESQL SCHEMA
-- =====================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- Enables fast fuzzy/text searching on product titles

-- ---------------------------------------------------------------------
-- 1. ENUM TYPES
-- ---------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE roleenum AS ENUM ('BUYER', 'SELLER', 'ADMIN');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE businesstypeenum AS ENUM ('INDIVIDUAL', 'SHOP', 'WAREHOUSE');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE verificationstatusenum AS ENUM ('UNVERIFIED', 'PENDING', 'APPROVED', 'REJECTED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE conditionenum AS ENUM ('Excellent', 'Very Good', 'Good', 'Fair', 'Poor');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE statusenum AS ENUM ('AVAILABLE', 'IN_CART', 'SOLD');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE paymentmethodenum AS ENUM ('WALLET', 'CARD');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE orderstatusenum AS ENUM ('PENDING', 'FUNDS_IN_ESCROW', 'SHIPPED', 'DELIVERED', 'COMPLETED_PAYOUT', 'DISPUTED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE tickettypeenum AS ENUM ('COMPLAINT', 'SUGGESTION', 'DISPUTE', 'OTHER_QUERY');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE ticketstatusenum AS ENUM ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- ---------------------------------------------------------------------
-- 2. AUTOMATED TIMESTAMP TRIGGER FUNCTION
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION update_timestamp_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';


-- ---------------------------------------------------------------------
-- 3. TABLES & CONSTRAINTS
-- ---------------------------------------------------------------------

-- USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR UNIQUE NOT NULL,
    hashed_password VARCHAR NULL,
    full_name VARCHAR NOT NULL,
    hex_code VARCHAR UNIQUE NOT NULL,
    role roleenum NOT NULL DEFAULT 'BUYER',
    avatar_url VARCHAR NULL,
    auth_provider VARCHAR NOT NULL DEFAULT 'local',
    google_id VARCHAR UNIQUE NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NULL
);

-- SELLER PROFILES TABLE
CREATE TABLE IF NOT EXISTS seller_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    shop_name VARCHAR NOT NULL,
    description VARCHAR NULL,
    phone_number VARCHAR NULL,
    address VARCHAR NULL,
    city VARCHAR NULL,
    business_type businesstypeenum NULL,
    cnic_number VARCHAR NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    verification_status verificationstatusenum NOT NULL DEFAULT 'UNVERIFIED',
    verified_at TIMESTAMP WITH TIME ZONE NULL,
    rating FLOAT DEFAULT 0.0,
    review_count INT DEFAULT 0
);

-- WALLETS TABLE
CREATE TABLE IF NOT EXISTS wallets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    balance FLOAT DEFAULT 0.0 CHECK (balance >= 0.0),
    currency VARCHAR DEFAULT 'PKR'
);

-- PRODUCTS TABLE
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    seller_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR NOT NULL,
    description TEXT NULL,
    price FLOAT NOT NULL CHECK (price >= 0.0),
    original_price FLOAT NULL,
    image_url VARCHAR NOT NULL,
    images VARCHAR[] DEFAULT '{}',
    category VARCHAR NOT NULL,
    department VARCHAR NOT NULL,
    size VARCHAR NOT NULL,
    brand VARCHAR NULL,
    condition conditionenum NOT NULL,
    condition_score INT NULL CHECK (condition_score >= 0 AND condition_score <= 100),
    is_ai_verified BOOLEAN DEFAULT FALSE,
    verification_hash VARCHAR NULL,
    verified_at TIMESTAMP WITH TIME ZONE NULL,
    tags VARCHAR[] DEFAULT '{}',
    status statusenum NOT NULL DEFAULT 'AVAILABLE'
);

-- SELLER VERIFICATION REQUESTS TABLE
CREATE TABLE IF NOT EXISTS seller_verification_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    seller_profile_id UUID NOT NULL REFERENCES seller_profiles(id) ON DELETE CASCADE,
    business_name VARCHAR NOT NULL,
    business_type businesstypeenum NOT NULL,
    phone_number VARCHAR NOT NULL,
    address VARCHAR NOT NULL,
    city VARCHAR NOT NULL,
    cnic_number VARCHAR NULL,
    cnic_front_url VARCHAR NOT NULL,
    cnic_back_url VARCHAR NOT NULL,
    shop_photo_urls VARCHAR[] DEFAULT '{}',
    business_reg_url VARCHAR NULL,
    status verificationstatusenum NOT NULL DEFAULT 'PENDING',
    rejection_reason VARCHAR NULL,
    reviewed_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NULL
);

-- VERIFICATION LOGS TABLE
CREATE TABLE IF NOT EXISTS verification_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    seller_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    similarity_score FLOAT NULL,
    detected_category VARCHAR NULL,
    liveness_passed BOOLEAN DEFAULT FALSE,
    verification_hash VARCHAR UNIQUE NOT NULL,
    is_successful BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ORDERS TABLE
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    buyer_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    seller_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    shipping_address VARCHAR NOT NULL,
    subtotal FLOAT NOT NULL CHECK (subtotal >= 0.0),
    escrow_fee FLOAT NOT NULL CHECK (escrow_fee >= 0.0),
    shipping_fee FLOAT NOT NULL CHECK (shipping_fee >= 0.0),
    total_amount FLOAT NOT NULL CHECK (total_amount >= 0.0),
    payment_method paymentmethodenum NOT NULL,
    status orderstatusenum NOT NULL DEFAULT 'PENDING'
);

-- CART ITEMS TABLE
CREATE TABLE IF NOT EXISTS cart_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id UUID UNIQUE NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- WISHLIST ITEMS TABLE
CREATE TABLE IF NOT EXISTS wishlist_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- REVIEWS TABLE
CREATE TABLE IF NOT EXISTS reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    buyer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT NULL,
    is_verified_purchase BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- SUPPORT TICKETS TABLE
CREATE TABLE IF NOT EXISTS support_tickets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    order_id UUID NULL REFERENCES orders(id) ON DELETE SET NULL,
    type tickettypeenum NOT NULL,
    subject VARCHAR NOT NULL,
    description TEXT NOT NULL,
    status ticketstatusenum NOT NULL DEFAULT 'OPEN',
    resolution_notes TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NULL
);

-- MESSAGES TABLE (CHAT)
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sender_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receiver_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_read BOOLEAN DEFAULT FALSE
);

-- ---------------------------------------------------------------------
-- 4. PERFORMANCE INDEXES (SINGLE & COMPOSITE)
-- ---------------------------------------------------------------------

-- User Lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_hex_code ON users(hex_code);
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);

-- Product Catalog Queries
CREATE INDEX IF NOT EXISTS idx_products_catalog_composite ON products(category, department, status, price);
CREATE INDEX IF NOT EXISTS idx_products_seller_status ON products(seller_id, status);
CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON products USING gin(name gin_trgm_ops);

-- Order Queries
CREATE INDEX IF NOT EXISTS idx_orders_buyer_status ON orders(buyer_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_seller_status ON orders(seller_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_product ON orders(product_id);

-- Chat History
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(sender_id, receiver_id, timestamp DESC);

-- Shopping & Wishlist
CREATE INDEX IF NOT EXISTS idx_cart_user ON cart_items(user_id);
CREATE INDEX IF NOT EXISTS idx_wishlist_user ON wishlist_items(user_id);

-- Reviews & Seller Verification
CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews(product_id);
CREATE INDEX IF NOT EXISTS idx_seller_vr_profile ON seller_verification_requests(seller_profile_id);

-- ---------------------------------------------------------------------
-- 5. AUTOMATED TIMESTAMP TRIGGERS
-- ---------------------------------------------------------------------

DROP TRIGGER IF EXISTS set_timestamp_users ON users;
CREATE TRIGGER set_timestamp_users
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

DROP TRIGGER IF EXISTS set_timestamp_svr ON seller_verification_requests;
CREATE TRIGGER set_timestamp_svr
BEFORE UPDATE ON seller_verification_requests
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

DROP TRIGGER IF EXISTS set_timestamp_support ON support_tickets;
CREATE TRIGGER set_timestamp_support
BEFORE UPDATE ON support_tickets
FOR EACH ROW EXECUTE FUNCTION update_timestamp_column();

-- =====================================================================
-- SCHEMA INITIALIZATION COMPLETE
-- =====================================================================
