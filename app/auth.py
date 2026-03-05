from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Form  # Добавил Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import hashlib
import hmac
import os
from typing import Optional
from app import models, schemas

router = APIRouter(tags=["authentication"])

SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey123")

def hash_password(password: str) -> str:
    salt = SECRET_KEY
    password_bytes = password.encode('utf-8')
    salt_bytes = salt.encode('utf-8')
    hashed = hmac.new(salt_bytes, password_bytes, hashlib.sha256)
    return hashed.hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

@router.post("/register")
def register(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(models.get_db)
):
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username exists")
    
    db_user = models.User(
        username=username,
        password_hash=hash_password(password)
    )
    db.add(db_user)
    db.commit()
    
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(key="session_id", value=username)
    return response

@router.post("/login")
def login(
    username: str = Form(...),  # Вместо user: schemas.UserLogin
    password: str = Form(...),  # Вместо user: schemas.UserLogin
    db: Session = Depends(models.get_db)
):
    db_user = db.query(models.User).filter(models.User.username == username).first()
    
    if not db_user or not verify_password(password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(key="session_id", value=username)
    return response

@router.post("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session_id")
    return response

def get_current_user(
    session_id: str = Cookie(None),
    db: Session = Depends(models.get_db)
) -> Optional[models.User]:
    if not session_id:
        return None
    return db.query(models.User).filter(models.User.username == session_id).first()
