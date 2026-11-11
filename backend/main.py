from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.session import get_db
from app.services.qr_service import QrService

app = FastAPI(
    title="Qbox Backend API",
    version="1.0.0",
    description="Commercial backend for Qbox shopkeeper and customer management.",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for mobile client & emulator access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API v1 routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    """Healthcheck endpoint to verify backend status."""
    return {
        "status": "healthy",
        "service": "qbox-backend",
        "environment": settings.ENVIRONMENT,
        "dev_target": settings.DEV_TARGET,
    }


@app.get("/join/{token}", response_class=HTMLResponse, tags=["Customer Onboarding"])
async def customer_join_landing(token: str, db: AsyncSession = Depends(get_db)):
    """
    Landing page for customers scanning a shop's static registration QR with their phone camera/browser.
    """
    shop = await QrService.lookup_public_shop_by_token(db=db, raw_token=token)
    if not shop:
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Qbox - Invalid QR</title>
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f6f8f7; margin: 0; padding: 24px; display: flex; justify-content: center; align-items: center; min-height: 80vh; }
                    .card { background: white; max-width: 420px; width: 100%; border-radius: 20px; padding: 32px 24px; text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.06); }
                    .badge { color: #d32f2f; font-weight: bold; font-size: 13px; text-transform: uppercase; }
                    h2 { color: #222; margin-top: 12px; }
                    p { color: #666; font-size: 14px; line-height: 1.5; }
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="badge">Registration Link Inactive</div>
                    <h2>QR Code Expired or Invalid</h2>
                    <p>This shop registration QR code is no longer active or the token is incorrect. Please ask the shopkeeper for their latest QR code.</p>
                </div>
            </body>
            </html>
            """,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return HTMLResponse(
        content=f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Qbox - Join {shop.shop_name}</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f6f8f7; margin: 0; padding: 24px; display: flex; justify-content: center; align-items: center; min-height: 80vh; }}
                .card {{ background: white; max-width: 440px; width: 100%; border-radius: 24px; padding: 32px 24px; text-align: center; box-shadow: 0 6px 24px rgba(23,107,91,0.08); border: 1.5px solid #176B5B; box-sizing: border-box; }}
                .logo {{ width: 56px; height: 56px; background: linear-gradient(135deg, #176B5B, #0F4B3F); border-radius: 16px; color: white; display: inline-flex; align-items: center; justify-content: center; font-size: 32px; font-weight: 900; margin-bottom: 16px; }}
                .badge {{ color: #176B5B; font-weight: 800; font-size: 11px; letter-spacing: 0.8px; text-transform: uppercase; background: #e2f1ed; display: inline-block; padding: 4px 12px; border-radius: 12px; }}
                h2 {{ color: #111; margin: 12px 0 6px; font-size: 22px; }}
                .address {{ color: #666; font-size: 13px; margin-bottom: 18px; }}
                .notice {{ background: #f6f8f7; border-radius: 14px; padding: 14px; font-size: 12px; color: #444; line-height: 1.5; margin-bottom: 20px; text-align: left; }}
                .token-box {{ font-family: monospace; background: #eef2f1; padding: 10px 14px; border-radius: 10px; font-size: 12px; color: #176B5B; word-break: break-all; margin-bottom: 18px; border: 1px dashed #176B5B; }}
                .btn {{ display: block; background: #176B5B; color: white; text-decoration: none; padding: 14px; border-radius: 12px; font-weight: bold; font-size: 15px; margin-bottom: 10px; cursor: pointer; border: none; width: 100%; box-sizing: border-box; }}
                .btn-secondary {{ display: block; background: #f0f4f3; color: #176B5B; text-decoration: none; padding: 12px; border-radius: 12px; font-weight: 600; font-size: 13px; margin-bottom: 16px; cursor: pointer; border: 1px solid #176B5B; width: 100%; box-sizing: border-box; }}
                .fallback-box {{ background: #fff8e1; border: 1px solid #ffe082; border-radius: 12px; padding: 14px; font-size: 12px; color: #795548; line-height: 1.5; text-align: left; margin-top: 14px; display: none; }}
                .fallback-box strong {{ color: #bf360c; display: block; margin-bottom: 4px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="logo">Q</div>
                <br>
                <div class="badge">Verified Qbox Merchant</div>
                <h2>{shop.shop_name}</h2>
                <div class="address">{shop.shop_address or 'Official Store'}</div>
                <div class="notice">
                    Connecting links your Qbox customer account to this store for digital credit ledger access. Initial balance is ₹0.00.
                </div>
                <div class="token-box">
                    <strong>Shop Token:</strong><br>{token}
                </div>
                <a id="open-app-btn" class="btn" href="intent://join/{token}#Intent;scheme=qbox;package=com.example.qbox_shopkeeper_demo;end" onclick="handleOpenApp(event)">
                    Open in Qbox App
                </a>
                <button id="copy-btn" class="btn-secondary" onclick="copyToken()">
                    📋 Copy Registration Token
                </button>
                <div id="install-notice" class="fallback-box">
                    <strong>App not opening?</strong>
                    Please verify that the <b>Qbox</b> app is installed on this Android phone. If recently installed, tap <b>Open in Qbox App</b> again, or launch Qbox manually and tap <b>Have a Shop QR Code? &rarr; Scan/Enter Token</b>.
                </div>
            </div>
            <script>
                function handleOpenApp(e) {{
                    setTimeout(function() {{
                        var notice = document.getElementById('install-notice');
                        if (notice) notice.style.display = 'block';
                    }}, 1500);
                }}

                function copyToken() {{
                    navigator.clipboard.writeText('{token}').then(function() {{
                        var btn = document.getElementById('copy-btn');
                        if (btn) {{
                            btn.innerText = '✅ Token Copied to Clipboard!';
                            setTimeout(function() {{ btn.innerText = '📋 Copy Registration Token'; }}, 2500);
                        }}
                    }}).catch(function() {{
                        alert('Token: {token}');
                    }});
                }}
            </script>
        </body>
        </html>
        """
    )


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to Qbox API",
        "docs": "/docs",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

