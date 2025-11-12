import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
import jwt
from bson import ObjectId

from database import db, create_document, get_documents

JWT_SECRET = os.getenv("JWT_SECRET", "secret-key-change-me")
JWT_ALG = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Photographer Portfolio API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# File storage setup
UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ----------------------
# Utility functions
# ----------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)

class TokenData(BaseModel):
    user_id: str
    role: str

async def get_current_user(authorization: Optional[str] = None) -> TokenData:
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        scheme, token = authorization.split(" ")
        if scheme.lower() != "bearer":
            raise ValueError("Invalid scheme")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return TokenData(user_id=payload.get("sub"), role=payload.get("role", "user"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(user: TokenData = Depends(get_current_user)) -> TokenData:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user

# ----------------------
# Models
# ----------------------
class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class AlbumIn(BaseModel):
    title: str
    description: Optional[str] = None
    cover_url: Optional[str] = None
    tags: List[str] = []

# ----------------------
# Routes
# ----------------------
@app.get("/")
def read_root():
    return {"message": "Photographer Portfolio API running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_name"] = getattr(db, "name", "Unknown")
            try:
                response["collections"] = db.list_collection_names()
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

# Auth
@app.post("/auth/register")
def register(payload: RegisterIn):
    existing = db["user"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # First registered user becomes admin automatically
    is_first = db["user"].count_documents({}) == 0
    user_doc = {
        "name": payload.name,
        "email": payload.email,
        "password_hash": hash_password(payload.password),
        "role": "admin" if is_first else "user",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    res = db["user"].insert_one(user_doc)
    uid = str(res.inserted_id)
    token = create_access_token({"sub": uid, "role": user_doc["role"]})
    return {"token": token, "user": {"id": uid, "name": user_doc["name"], "email": user_doc["email"], "role": user_doc["role"]}}

@app.post("/auth/login")
def login(payload: LoginIn):
    user = db["user"].find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    uid = str(user["_id"]) 
    token = create_access_token({"sub": uid, "role": user.get("role", "user")})
    return {"token": token, "user": {"id": uid, "name": user.get("name"), "email": user.get("email"), "role": user.get("role", "user")}}

@app.get("/me")
def me(user: TokenData = Depends(get_current_user)):
    u = db["user"].find_one({"_id": ObjectId(user.user_id)})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": str(u["_id"]), "name": u.get("name"), "email": u.get("email"), "role": u.get("role", "user")}

# Albums
@app.get("/albums")
def list_albums():
    albums = get_documents("album", {})
    out = []
    for a in albums:
        a["id"] = str(a.pop("_id"))
        out.append(a)
    return out

@app.post("/albums")
def create_album(payload: AlbumIn, user: TokenData = Depends(require_admin)):
    doc = {
        "title": payload.title,
        "description": payload.description,
        "cover_url": payload.cover_url,
        "tags": payload.tags or [],
        "owner_id": user.user_id,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    res_id = create_document("album", doc)
    return {"id": res_id, **doc}

@app.get("/albums/{album_id}")
def get_album(album_id: str):
    a = db["album"].find_one({"_id": ObjectId(album_id)})
    if not a:
        raise HTTPException(404, "Album not found")
    a["id"] = str(a.pop("_id"))
    photos = list(db["photo"].find({"album_id": album_id}))
    for p in photos:
        p["id"] = str(p.pop("_id"))
    a["photos"] = photos
    return a

# Photos upload
@app.post("/albums/{album_id}/photos")
async def upload_photo(album_id: str, file: UploadFile = File(...), title: Optional[str] = Form(None), description: Optional[str] = Form(None), user: TokenData = Depends(require_admin)):
    # Validate album
    if not db["album"].find_one({"_id": ObjectId(album_id)}):
        raise HTTPException(404, "Album not found")

    ext = os.path.splitext(file.filename)[1]
    safe_name = f"{ObjectId()}{ext}"
    album_dir = os.path.join(UPLOAD_DIR, album_id)
    os.makedirs(album_dir, exist_ok=True)
    dest_path = os.path.join(album_dir, safe_name)

    with open(dest_path, "wb") as f:
        f.write(await file.read())

    file_url = f"/uploads/{album_id}/{safe_name}"

    doc = {
        "album_id": album_id,
        "title": title,
        "description": description,
        "file_url": file_url,
        "file_name": file.filename,
        "file_size": os.path.getsize(dest_path),
        "downloadable": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    res_id = create_document("photo", doc)
    return {"id": res_id, **doc}

@app.get("/photos/{photo_id}/download")
def download_photo(photo_id: str):
    p = db["photo"].find_one({"_id": ObjectId(photo_id)})
    if not p:
        raise HTTPException(404, "Photo not found")
    file_url = p.get("file_url")
    # file_url format: /uploads/<album_id>/<name>
    fs_path = os.path.join(os.getcwd(), file_url.lstrip("/"))
    if not os.path.exists(fs_path):
        raise HTTPException(404, "File not found")
    return FileResponse(fs_path, filename=p.get("file_name") or os.path.basename(fs_path), media_type="application/octet-stream")

@app.get("/albums/{album_id}/download")
def download_album_zip(album_id: str):
    import zipfile
    a = db["album"].find_one({"_id": ObjectId(album_id)})
    if not a:
        raise HTTPException(404, "Album not found")
    photos = list(db["photo"].find({"album_id": album_id}))
    if not photos:
        raise HTTPException(404, "No photos to download")

    def iterfile():
        memfile = BytesIO()
        with zipfile.ZipFile(memfile, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            for p in photos:
                file_url = p.get("file_url")
                fs_path = os.path.join(os.getcwd(), file_url.lstrip("/"))
                if os.path.exists(fs_path):
                    arcname = p.get("file_name") or os.path.basename(fs_path)
                    zf.write(fs_path, arcname=arcname)
        memfile.seek(0)
        yield from memfile

    headers = {"Content-Disposition": f"attachment; filename=album-{album_id}.zip"}
    return StreamingResponse(iterfile(), media_type="application/zip", headers=headers)

