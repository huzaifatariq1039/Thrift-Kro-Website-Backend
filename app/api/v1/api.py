from fastapi import APIRouter
from app.api.v1.routers import auth, users, products, orders, wallet, vto, chat, reviews, ai, stores, sellers, shopping, support, admin

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(wallet.router, prefix="/wallet", tags=["wallet"])
api_router.include_router(vto.router, prefix="/vto", tags=["vto"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(stores.router, prefix="/stores", tags=["stores"])
api_router.include_router(sellers.router, prefix="/sellers", tags=["sellers"])
api_router.include_router(shopping.router, prefix="/shopping", tags=["shopping"])
api_router.include_router(support.router, prefix="/support", tags=["support"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
