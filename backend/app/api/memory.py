"""Long-term memory: list / add / forget items and switch memory on or off. Other users' items are 404."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import Memory, User
from app.features.memory import extract, store
from app.schemas import CamelModel

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryIn(CamelModel):
    content: str = Field(min_length=1, max_length=store.MAX_CONTENT)


class MemorySettingsIn(CamelModel):
    enabled: bool


@router.get("")
def get_memory(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {"enabled": store.is_enabled(user), "items": [store.item_out(m) for m in store.list_memories(db, user.id)]}


@router.post("")
def add_memory(body: MemoryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    content = " ".join(body.content.split())
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Memory can't be empty")
    if extract.is_secret(content):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Memory can't hold passwords, keys, account numbers or contact details")
    memory = store.find_duplicate(db, user.id, content) or store.add(db, user.id, content)
    db.commit()
    return store.item_out(memory)


@router.put("/settings")
def update_settings(body: MemorySettingsIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> dict:
    user.memory_enabled = body.enabled
    db.commit()
    return {"enabled": store.is_enabled(user)}


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    memory = db.get(Memory, memory_id)
    if memory is None or memory.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory not found")
    db.delete(memory)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def forget_everything(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    db.execute(delete(Memory).where(Memory.user_id == user.id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
