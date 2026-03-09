from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import redis
import json
import random
import string
import os
import sys
import logging
from typing import Optional
from app import models, schemas, auth

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/links", tags=["links"])

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
UNUSED_DAYS = int(os.getenv("UNUSED_DAYS", "30"))

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=int(REDIS_PORT),
    decode_responses=True
)

def generate_short_code(length: int = 6) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def is_expired(expires_at: Optional[datetime]) -> bool:
    if not expires_at:
        return False
    return datetime.utcnow() > expires_at

@router.post("/shorten")
def create_short_link(
    link_data: schemas.LinkCreate,
    current_user = Depends(auth.get_current_user),
    db: Session = Depends(models.get_db)
):
    if link_data.custom_alias:
        if db.query(models.Link).filter(models.Link.short_code == link_data.custom_alias).first():
            raise HTTPException(status_code=400, detail="Alias already exists")
        short_code = link_data.custom_alias
    else:
        while True:
            short_code = generate_short_code()
            if not db.query(models.Link).filter(models.Link.short_code == short_code).first():
                break
    
    db_link = models.Link(
        short_code=short_code,
        original_url=str(link_data.original_url),
        custom_alias=link_data.custom_alias,
        expires_at=link_data.expires_at,
        user_id=current_user.id if current_user else None,
        username=current_user.username if current_user else "anonymous")
    
    db.add(db_link)
    db.commit()
    db.refresh(db_link)
    
    redis_client.setex(
        f"link:{short_code}",
        3600,
        json.dumps({"url": db_link.original_url, "clicks": 0})
    )
    
    return {
        "short_code": short_code,
        "short_url": f"{BASE_URL}/links/{short_code}",
        "original_url": db_link.original_url,
        "created_at": db_link.created_at,
        "expires_at": db_link.expires_at,
        "clicks": 0,
        "created_by": db_link.username
    }

@router.get("/search")
def search_links(original_url: str, db: Session = Depends(models.get_db)):
    from sqlalchemy import text
    
    result = db.execute(
        text("""
            SELECT short_code, original_url, username 
            FROM links 
            WHERE original_url ILIKE :pattern AND is_active = true
        """),
        {"pattern": f"%{original_url}%"}
    ).fetchall()
    
    return [
        {
            "short_code": r[0],
            "short_url": f"{BASE_URL}/links/{r[0]}",
            "original_url": r[1],
            "created_by": r[2]
        }
        for r in result
    ]

@router.get("/expired/history")
def get_expired_links(db: Session = Depends(models.get_db)):
    expired = db.query(models.Link).filter(models.Link.is_active == False).all()
    
    return [
        {
            "short_code": l.short_code,
            "original_url": l.original_url,
            "created_at": l.created_at,
            "created_by": l.username,
            "expires_at": l.expires_at,
            "clicks": l.clicks,
            "last_accessed": l.last_accessed,
            "reason": "expired" if l.expires_at and l.expires_at < datetime.utcnow() else "unused"}
        for l in expired
    ]

@router.get("/{short_code}")
def redirect_to_url(short_code: str, db: Session = Depends(models.get_db)):
    cached = redis_client.get(f"link:{short_code}")
    
    if cached:
        data = json.loads(cached)
        original_url = data["url"]
        
        db_link = db.query(models.Link).filter(models.Link.short_code == short_code).first()
        if db_link:
            db_link.clicks += 1
            db_link.last_accessed = datetime.utcnow()
            db.commit()
            
            redis_client.setex(
                f"link:{short_code}",
                3600,
                json.dumps({"url": original_url, "clicks": db_link.clicks})
            )
    else:
        db_link = db.query(models.Link).filter(
            models.Link.short_code == short_code,
            models.Link.is_active == True
        ).first()
        
        if not db_link:
            raise HTTPException(status_code=404, detail="Link not found")
        
        if is_expired(db_link.expires_at):
            db_link.is_active = False
            db.commit()
            redis_client.delete(f"link:{short_code}")
            raise HTTPException(status_code=410, detail="Link expired")
        
        original_url = db_link.original_url
        db_link.clicks += 1
        db_link.last_accessed = datetime.utcnow()
        db.commit()
        
        redis_client.setex(
            f"link:{short_code}",
            3600,
            json.dumps({"url": original_url, "clicks": db_link.clicks})
        )
    
    return RedirectResponse(url=original_url)

@router.delete("/{short_code}")
def delete_link(
    short_code: str,
    current_user = Depends(auth.get_current_user),
    db: Session = Depends(models.get_db)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    db_link = db.query(models.Link).filter(models.Link.short_code == short_code).first()
    
    if not db_link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    if db_link.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your link")
    
    db_link.is_active = False
    db.commit()
    
    redis_client.delete(f"link:{short_code}")
    redis_client.delete(f"stats:{short_code}")
    
    return {"message": "Link deleted"}

@router.put("/{short_code}")
def update_link(
    short_code: str,
    link_data: schemas.LinkUpdate,
    current_user = Depends(auth.get_current_user),
    db: Session = Depends(models.get_db)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    db_link = db.query(models.Link).filter(models.Link.short_code == short_code).first()
    
    if not db_link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    if db_link.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your link")
    
    db_link.original_url = str(link_data.original_url)
    db.commit()
    db.refresh(db_link)
    
    redis_client.delete(f"link:{short_code}")
    redis_client.delete(f"stats:{short_code}")
    
    return {
        "short_code": short_code,
        "short_url": f"{BASE_URL}/links/{short_code}",
        "original_url": db_link.original_url,
        "created_at": db_link.created_at,
        "expires_at": db_link.expires_at,
        "clicks": db_link.clicks,
        "created_by": db_link.username
    }

@router.get("/{short_code}/stats")
def get_link_stats(short_code: str, db: Session = Depends(models.get_db)):
    cached = redis_client.get(f"stats:{short_code}")
    if cached:
        return json.loads(cached)
    
    db_link = db.query(models.Link).filter(models.Link.short_code == short_code).first()
    
    if not db_link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    stats = {
        "short_code": db_link.short_code,
        "short_url": f"{BASE_URL}/links/{db_link.short_code}",
        "original_url": db_link.original_url,
        "created_at": db_link.created_at.isoformat(),
        "expires_at": db_link.expires_at.isoformat() if db_link.expires_at else None,
        "clicks": db_link.clicks,
        "created_by": db_link.username,
        "last_accessed": db_link.last_accessed.isoformat() if db_link.last_accessed else None
    }
    
    redis_client.setex(f"stats:{short_code}", 300, json.dumps(stats, default=str))
    return stats
