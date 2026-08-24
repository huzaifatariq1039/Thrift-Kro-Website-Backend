from sqlalchemy import text
from app.core.database import engine

def run():
    conn = engine.connect()
    try:
        conn.execute(text("ALTER TABLE seller_verification_requests ADD COLUMN IF NOT EXISTS shop_photo_urls JSON DEFAULT '[]'::json;"))
        conn.execute(text("ALTER TABLE seller_verification_requests ADD COLUMN IF NOT EXISTS products_proof JSON DEFAULT '[]'::json;"))
        conn.execute(text("ALTER TABLE seller_verification_requests ADD COLUMN IF NOT EXISTS ai_verified BOOLEAN DEFAULT FALSE;"))
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    run()
