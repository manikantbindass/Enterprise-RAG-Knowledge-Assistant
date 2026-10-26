import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from . import providers
from .database import (
    DATA,
    Audit,
    Base,
    Chunk,
    Conversation,
    Document,
    LoginSession,
    Message,
    Organization,
    Query,
    Session,
    User,
    engine,
    uid,
)
from .ingestion import MAX_BYTES, validate, worker
from .retrieval import search

log = logging.getLogger("rag.runtime")
hasher = PasswordHash.recommended()
DUMMY_HASH = hasher.hash("not-a-real-account-password")
COOKIE = "rag_session"
ORIGINS = set(
    os.getenv(
        "RAG_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
)
SECURE = os.getenv("RAG_SECURE_COOKIES", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    task = asyncio.create_task(worker())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    await engine.dispose()


app = FastAPI(title="Enterprise RAG — local runtime", version="2.0.0", lifespan=lifespan)
attempts = defaultdict(deque)


@app.middleware("http")
async def security(request: Request, call_next):
    request_id = secrets.token_hex(8)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        # Require browser Origin even for login to prevent login CSRF.
        if request.headers.get("origin") not in ORIGINS:
            return JSONResponse({"detail": "Request origin is not allowed."}, status_code=403)
    host = request.client.host if request.client else "unknown"
    # Single-machine limits. Configure shared Redis limits before multi-instance deployment.
    auth = request.url.path.endswith(("/login", "/register"))
    key = (host, "auth" if auth else "api")
    bucket = attempts[key]
    current = time.monotonic()
    while bucket and bucket[0] < current - 60:
        bucket.popleft()
    if len(bucket) >= (15 if auth else 240):
        return JSONResponse(
            {"detail": "Too many requests. Try again in a minute."},
            status_code=429,
            headers={"Retry-After": "60"},
        )
    bucket.append(current)
    if len(attempts) > 5000:
        for old_key in list(attempts):
            if not attempts[old_key] or attempts[old_key][-1] < current - 60:
                del attempts[old_key]
    response = await call_next(request)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin",
            "Cache-Control": "no-store",
            "X-Request-ID": request_id,
        }
    )
    return response


async def database():
    async with Session() as db:
        yield db


async def current_user(request: Request, db=Depends(database)):
    token = request.cookies.get(COOKIE, "")
    if not token:
        raise HTTPException(401, "Sign in to continue.")
    session = await db.get(LoginSession, hashlib.sha256(token.encode()).hexdigest())
    if not session or session.expires <= time.time():
        raise HTTPException(401, "Your session has expired. Sign in again.")
    user = await db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "This account is inactive.")
    return user


def admin(user):
    if user.role != "admin":
        raise HTTPException(403, "Organization administrator access is required.")


def editor(user):
    if user.role == "viewer":
        raise HTTPException(403, "Viewers cannot modify knowledge documents.")


def profile(user):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "active": user.active,
        "created_at": user.created_at,
    }


def audit(db, user, action, target=""):
    db.add(Audit(org_id=user.org_id, user_id=user.id, action=action, target=target))


async def issue_session(db, user, response):
    token = secrets.token_urlsafe(48)
    db.add(
        LoginSession(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            user_id=user.id,
            expires=time.time() + 28800,
        )
    )
    await db.execute(delete(LoginSession).where(LoginSession.expires < time.time()))
    response.set_cookie(
        COOKIE,
        token,
        max_age=28800,
        httponly=True,
        secure=SECURE,
        samesite="lax",
        path="/",
    )


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=12, max_length=128)


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=100)
    organization: str = Field(min_length=1, max_length=100)


@app.get("/health")
async def health(db=Depends(database)):
    await db.execute(select(1))
    return {
        "status": "ok",
        "runtime": "local",
        "storage": "sqlite",
        "provider": providers.configuration(),
    }


@app.post("/api/v2/auth/register", status_code=201)
async def register(body: Registration, response: Response, db=Depends(database)):
    if os.getenv("RAG_ALLOW_REGISTRATION", "true").lower() != "true":
        raise HTTPException(403, "Self-service registration is disabled.")
    organization = Organization(name=body.organization.strip())
    db.add(organization)
    await db.flush()
    user = User(
        org_id=organization.id,
        email=body.email.strip().lower(),
        name=body.name.strip(),
        password=await asyncio.to_thread(hasher.hash, body.password),
        role="admin",
    )
    db.add(user)
    try:
        await db.flush()
        await issue_session(db, user, response)
        audit(db, user, "account.registered")
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "An account already uses that email.") from None
    return profile(user)


@app.post("/api/v2/auth/login")
async def login(body: Credentials, response: Response, request: Request, db=Depends(database)):
    user = await db.scalar(select(User).where(User.email == body.email.strip().lower()))
    valid = await asyncio.to_thread(
        hasher.verify, body.password, user.password if user else DUMMY_HASH
    )
    if not user or not valid or not user.active:
        raise HTTPException(401, "Email or password is incorrect.")
    old = request.cookies.get(COOKIE)
    if old:
        await db.execute(
            delete(LoginSession).where(
                LoginSession.token_hash == hashlib.sha256(old.encode()).hexdigest()
            )
        )
    await issue_session(db, user, response)
    audit(db, user, "session.created")
    await db.commit()
    return profile(user)


@app.post("/api/v2/auth/logout")
async def logout(
    request: Request,
    response: Response,
    user=Depends(current_user),
    db=Depends(database),
):
    digest = hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest()
    await db.execute(delete(LoginSession).where(LoginSession.token_hash == digest))
    audit(db, user, "session.revoked")
    await db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/v2/me")
async def me(user=Depends(current_user), db=Depends(database)):
    organization = await db.get(Organization, user.org_id)
    return {
        **profile(user),
        "organization": organization.name,
        "provider": providers.configuration(),
    }


def document_json(doc, count=0):
    return {
        "id": doc.id,
        "name": doc.name,
        "size": doc.size,
        "department": doc.department,
        "status": doc.status,
        "error": doc.error,
        "created_at": doc.created_at,
        "chunks": count,
    }


async def authorized_document(db, user, doc_id):
    doc = await db.scalar(
        select(Document).where(Document.id == doc_id, Document.org_id == user.org_id)
    )
    if not doc:
        raise HTTPException(404, "Document not found.")
    return doc


@app.get("/api/v2/documents")
async def documents(user=Depends(current_user), db=Depends(database)):
    rows = await db.execute(
        select(Document, func.count(Chunk.id))
        .outerjoin(Chunk, Chunk.doc_id == Document.id)
        .where(Document.org_id == user.org_id)
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    )
    return [document_json(doc, count) for doc, count in rows]


@app.post("/api/v2/documents", status_code=202)
async def upload(
    file: UploadFile = File(...),
    department: str = Form("General"),
    user=Depends(current_user),
    db=Depends(database),
):
    editor(user)
    name = Path((file.filename or "document").replace("\\", "/")).name[:200]
    if len(department) > 60:
        raise HTTPException(422, "Department must be at most 60 characters.")
    data = await file.read(MAX_BYTES + 1)
    await file.close()
    try:
        await asyncio.to_thread(validate, data, Path(name).suffix.lower())
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, str(exc)[:300]) from None
    digest = hashlib.sha256(data).hexdigest()
    if await db.scalar(
        select(Document.id).where(Document.org_id == user.org_id, Document.digest == digest)
    ):
        raise HTTPException(409, "This document is already in your knowledge library.")
    doc = Document(
        id=uid(),
        org_id=user.org_id,
        owner_id=user.id,
        name=name,
        size=len(data),
        digest=digest,
        department=department,
    )
    path = DATA / "uploads" / doc.id
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, data)
    try:
        db.add(doc)
        audit(db, user, "document.uploaded", doc.id)
        await db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return document_json(doc)


@app.get("/api/v2/documents/{doc_id}")
async def preview(doc_id: str, user=Depends(current_user), db=Depends(database)):
    doc = await authorized_document(db, user, doc_id)
    chunks = (
        await db.scalars(
            select(Chunk)
            .where(Chunk.doc_id == doc.id, Chunk.org_id == user.org_id)
            .order_by(Chunk.position)
        )
    ).all()
    return {
        **document_json(doc, len(chunks)),
        "sections": [
            {"id": c.id, "page": c.page, "position": c.position, "content": c.content}
            for c in chunks
        ],
    }


@app.get("/api/v2/documents/{doc_id}/download")
async def download(doc_id: str, user=Depends(current_user), db=Depends(database)):
    doc = await authorized_document(db, user, doc_id)
    path = DATA / "uploads" / doc.id
    if not path.exists():
        raise HTTPException(404, "Original file is unavailable.")
    audit(db, user, "document.downloaded", doc.id)
    await db.commit()
    return FileResponse(path, filename=doc.name, media_type="application/octet-stream")


@app.delete("/api/v2/documents/{doc_id}")
async def remove_document(doc_id: str, user=Depends(current_user), db=Depends(database)):
    editor(user)
    doc = await authorized_document(db, user, doc_id)
    await db.delete(doc)
    audit(db, user, "document.deleted", doc_id)
    await db.commit()
    (DATA / "uploads" / doc_id).unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/v2/documents/{doc_id}/reindex")
async def reindex(doc_id: str, user=Depends(current_user), db=Depends(database)):
    editor(user)
    doc = await authorized_document(db, user, doc_id)
    if doc.status in {"extracting", "chunking"}:
        raise HTTPException(409, "Document is currently processing.")
    doc.status, doc.error = "queued", None
    audit(db, user, "document.reindex", doc_id)
    await db.commit()
    return document_json(doc)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    doc_ids: list[str] = Field(default_factory=list, max_length=30)
    top_k: int = Field(default=5, ge=1, le=10)


@app.post("/api/v2/search")
async def search_documents(body: SearchRequest, user=Depends(current_user), db=Depends(database)):
    return await search(db, user.org_id, body.query, body.doc_ids, body.top_k)


class ConversationTitle(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=150)


async def authorized_conversation(db, user, conversation_id):
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.org_id == user.org_id,
            Conversation.user_id == user.id,
        )
    )
    if not conv:
        raise HTTPException(404, "Conversation not found.")
    return conv


@app.get("/api/v2/conversations")
async def conversations(user=Depends(current_user), db=Depends(database)):
    convs = (
        await db.scalars(
            select(Conversation)
            .where(Conversation.org_id == user.org_id, Conversation.user_id == user.id)
            .order_by(Conversation.created_at.desc())
        )
    ).all()
    return [{"id": c.id, "title": c.title, "created_at": c.created_at} for c in convs]


@app.post("/api/v2/conversations", status_code=201)
async def create_conversation(
    body: ConversationTitle, user=Depends(current_user), db=Depends(database)
):
    conv = Conversation(org_id=user.org_id, user_id=user.id, title=body.title)
    db.add(conv)
    await db.commit()
    return {"id": conv.id, "title": conv.title, "created_at": conv.created_at}


@app.patch("/api/v2/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    body: ConversationTitle,
    user=Depends(current_user),
    db=Depends(database),
):
    conv = await authorized_conversation(db, user, conversation_id)
    conv.title = body.title
    await db.commit()
    return {"ok": True}


@app.delete("/api/v2/conversations/{conversation_id}")
async def remove_conversation(
    conversation_id: str, user=Depends(current_user), db=Depends(database)
):
    conv = await authorized_conversation(db, user, conversation_id)
    await db.delete(conv)
    await db.commit()
    return {"ok": True}


@app.get("/api/v2/conversations/{conversation_id}/messages")
async def messages(conversation_id: str, user=Depends(current_user), db=Depends(database)):
    await authorized_conversation(db, user, conversation_id)
    rows = (
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
    ).all()
    # Deleted documents must not continue to disclose excerpts through stored citations.
    permitted = set(
        (await db.scalars(select(Document.id).where(Document.org_id == user.org_id))).all()
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "status": m.status,
            "sources": [s for s in m.sources if s["doc_id"] in permitted],
            "created_at": m.created_at,
        }
        for m in rows
    ]


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/v2/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SearchRequest,
    request: Request,
    user=Depends(current_user),
    db=Depends(database),
):
    conv = await authorized_conversation(db, user, conversation_id)
    sources = await search(db, user.org_id, body.query, body.doc_ids, body.top_k)
    history_rows = (
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conv.id, Message.status == "completed")
            .order_by(Message.created_at.desc())
            .limit(6)
        )
    ).all()
    history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]
    if conv.title == "New conversation":
        conv.title = body.query[:100]
    db.add(Message(conversation_id=conv.id, role="user", content=body.query))
    assistant = Message(
        id=uid(),
        conversation_id=conv.id,
        role="assistant",
        content="",
        sources=[],
        status="generating",
    )
    db.add(assistant)
    audit(db, user, "chat.started", conv.id)
    await db.commit()
    org_id, user_id, assistant_id = user.org_id, user.id, assistant.id

    async def events():
        answer, status = "", "completed"
        started = time.perf_counter()
        config = providers.configuration()
        try:
            yield sse("meta", {"id": assistant_id, "mode": config["mode"]})
            yield sse("sources", sources)
            if not sources:
                answer = "I could not find supporting evidence in your permitted documents. Try a more specific question or upload relevant knowledge."
                yield sse("token", answer)
            elif not config["configured"]:
                answer = "Retrieved excerpts · no AI model configured\n\n" + "\n\n".join(
                    f"[{i + 1}] {s['excerpt']}" for i, s in enumerate(sources)
                )
                yield sse("token", answer)
            else:
                async with asyncio.timeout(120):
                    async for token in providers.generate(body.query, sources, history):
                        if await request.is_disconnected():
                            status = "cancelled"
                            break
                        answer += token
                        yield sse("token", token)
                invalid = [
                    n for n in re.findall(r"\[(\d+)\]", answer) if not 1 <= int(n) <= len(sources)
                ]
                if invalid:
                    status = "failed"
                    yield sse(
                        "error",
                        "The model produced an invalid citation. Treat this response as unverified.",
                    )
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception:
            status = "failed"
            log.exception("generation_failed conversation=%s", conversation_id)
            yield sse(
                "error",
                "Generation failed. Check the server provider configuration and retry.",
            )
        finally:
            # Independent session remains available when the client disconnects.
            async def persist():
                async with Session() as output:
                    record = await output.get(Message, assistant_id)
                    if record:
                        record.content, record.status, record.sources = (
                            answer,
                            status,
                            sources,
                        )
                        output.add(
                            Query(
                                org_id=org_id,
                                latency_ms=(time.perf_counter() - started) * 1000,
                                found=bool(sources),
                                provider=config["provider"],
                            )
                        )
                        output.add(
                            Audit(
                                org_id=org_id,
                                user_id=user_id,
                                action=f"chat.{status}",
                                target=conversation_id,
                            )
                        )
                        await output.commit()

            await asyncio.shield(persist())
        yield sse("done", {"id": assistant_id, "status": status})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )


@app.get("/api/v2/analytics")
async def analytics(user=Depends(current_user), db=Depends(database)):
    docs = (await db.scalars(select(Document).where(Document.org_id == user.org_id))).all()
    queries = (await db.scalars(select(Query).where(Query.org_id == user.org_id))).all()
    daily = defaultdict(int)
    for q in queries:
        daily[q.created_at[:10]] += 1
    departments = defaultdict(int)
    for doc in docs:
        departments[doc.department] += 1
    return {
        "documents": len(docs),
        "indexed": sum(d.status == "indexed" for d in docs),
        "pending": sum(d.status in {"queued", "extracting", "chunking"} for d in docs),
        "failed": sum(d.status == "failed" for d in docs),
        "storage_bytes": sum(d.size for d in docs),
        "chunks": await db.scalar(select(func.count(Chunk.id)).where(Chunk.org_id == user.org_id)),
        "queries": len(queries),
        "average_latency_ms": round(sum(q.latency_ms for q in queries) / max(1, len(queries))),
        "users": await db.scalar(
            select(func.count(User.id)).where(User.org_id == user.org_id, User.active.is_(True))
        ),
        "daily": [{"date": k, "queries": v} for k, v in sorted(daily.items())],
        "departments": [{"name": k, "documents": v} for k, v in departments.items()],
        "cost": None,
        "tokens": None,
    }


@app.get("/api/v2/admin/users")
async def members(user=Depends(current_user), db=Depends(database)):
    admin(user)
    return [
        profile(u) for u in (await db.scalars(select(User).where(User.org_id == user.org_id))).all()
    ]


class MemberCreate(Credentials):
    name: str = Field(min_length=1, max_length=100)
    role: Literal["admin", "member", "viewer"] = "member"


@app.post("/api/v2/admin/users", status_code=201)
async def add_member(body: MemberCreate, user=Depends(current_user), db=Depends(database)):
    admin(user)
    member = User(
        org_id=user.org_id,
        name=body.name,
        email=body.email.lower(),
        role=body.role,
        password=await asyncio.to_thread(hasher.hash, body.password),
    )
    db.add(member)
    audit(db, user, "member.created", body.email)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "An account already uses that email.") from None
    return profile(member)


class MemberPatch(BaseModel):
    active: bool
    role: Literal["admin", "member", "viewer"]


@app.patch("/api/v2/admin/users/{member_id}")
async def update_member(
    member_id: str, body: MemberPatch, user=Depends(current_user), db=Depends(database)
):
    admin(user)
    member = await db.scalar(select(User).where(User.id == member_id, User.org_id == user.org_id))
    if not member:
        raise HTTPException(404, "Member not found.")
    if member.id == user.id:
        raise HTTPException(409, "You cannot deactivate or change your own administrator role.")
    member.active, member.role = body.active, body.role
    await db.execute(delete(LoginSession).where(LoginSession.user_id == member.id))
    audit(db, user, "member.updated", member.id)
    await db.commit()
    return profile(member)


@app.get("/api/v2/admin/audit")
async def audit_records(user=Depends(current_user), db=Depends(database)):
    admin(user)
    rows = (
        await db.scalars(
            select(Audit)
            .where(Audit.org_id == user.org_id)
            .order_by(Audit.created_at.desc())
            .limit(100)
        )
    ).all()
    return [
        {"id": a.id, "action": a.action, "target": a.target, "created_at": a.created_at}
        for a in rows
    ]
