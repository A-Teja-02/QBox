from fastapi import APIRouter
from app.api.v1 import auth, customer, ledger, public, shops

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(shops.router, prefix="/shops", tags=["Shops & Registration QR"])
api_router.include_router(public.router, prefix="/public", tags=["Public Shop QR Lookup"])
api_router.include_router(customer.router, prefix="/customer", tags=["Customer Management"])
api_router.include_router(ledger.router, tags=["Udhaar Ledger"])
