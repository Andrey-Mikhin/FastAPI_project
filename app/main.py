from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
import asyncio
from datetime import datetime, timedelta
import os
from app import auth, links, models
from app.auth import get_current_user

app = FastAPI(title="URL Shortener")

UNUSED_DAYS = int(os.getenv("UNUSED_DAYS", "30"))

app.include_router(auth.router)
app.include_router(links.router)

async def cleanup_task():
    while True:
        await asyncio.sleep(3600)
        db = models.SessionLocal()
        try:
            expired = db.query(models.Link).filter(
                models.Link.expires_at < datetime.utcnow(),
                models.Link.is_active == True
            ).all()
            
            for link in expired:
                link.is_active = False
                links.redis_client.delete(f"link:{link.short_code}")
                links.redis_client.delete(f"stats:{link.short_code}")
            
            unused_date = datetime.utcnow() - timedelta(days=UNUSED_DAYS)
            unused = db.query(models.Link).filter(
                models.Link.last_accessed < unused_date,
                models.Link.is_active == True
            ).all()
            
            for link in unused:
                link.is_active = False
                links.redis_client.delete(f"link:{link.short_code}")
                links.redis_client.delete(f"stats:{link.short_code}")
            
            db.commit()
        finally:
            db.close()

@app.on_event("startup")
async def startup():
    asyncio.create_task(cleanup_task())

@app.get("/", response_class=HTMLResponse)
def root(current_user = Depends(get_current_user)):
    username = current_user.username if current_user else "anonymous"
    return f"""
    <html>
        <head>
            <title>URL Shortener</title>
            <style>
                body {{ font-family: Arial; margin: 40px; }}
                .info {{ background: #f0f0f0; padding: 10px; margin: 10px 0; }}
                .button {{ display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>URL Shortener API</h1>
            <div class="info">
                <strong>Current user:</strong> {username}
            </div>
            
            <p>Документация API доступна в Swagger UI:</p>
            <a href="/docs" class="button">Перейти к документации API →</a>
            
            <p style="margin-top: 30px;">Используйте Swagger UI для тестирования всех эндпоинтов.</p>
        </body>
    </html>
    """

@app.get("/me")
def me(current_user = Depends(get_current_user)):
    if current_user:
        return {
            "authenticated": True,
            "username": current_user.username,
            "created_at": current_user.created_at
        }
    return {"authenticated": False, "username": "anonymous"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
