"""POST /api/verify/{messageId}: re-check a saved answer against its stored sources and persist the result."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import Conversation, Message, User
from app.features.verify import nli, verifier

router = APIRouter(prefix="/verify", tags=["verify"])

MODEL_WAIT_S = 90.0  # a first run may need to download the model (~90 MB)
UNAVAILABLE = "The verification model isn't available — its first run needs internet access to download it"
NOT_FOUND = "Message not found"


def _owned_message(db: Session, message_id: str, user: User) -> Message:
    msg = db.get(Message, message_id)
    conv = db.get(Conversation, msg.conversation_id) if msg is not None else None
    if msg is None or conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return msg


@router.post("/{message_id}")
def verify_message(message_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    msg = _owned_message(db, message_id, user)
    if msg.role != "assistant":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only assistant answers can be verified")

    # Live answers are checked against the full pages/chunks; a saved message only keeps 400-char snippets.
    content, sources = msg.content or "", list(msg.sources or [])
    workspace = (msg.meta or {}).get("workspace")
    skip = verifier.code_sources(sources, workspace.get("id") if isinstance(workspace, dict) else None)
    contexts = verifier.contexts_from_sources(sources)
    db.rollback()  # don't hold a pooled connection while the model loads (up to MODEL_WAIT_S) and scores
    try:
        result = verifier.verify(content, contexts, None, skip_sources=skip)  # enough when nothing is checkable
    except verifier.ScorerRequired:
        scorer = nli.get(MODEL_WAIT_S)
        if scorer is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None
        result = verifier.verify(content, contexts, scorer, skip_sources=skip)

    msg = _owned_message(db, message_id, user)  # re-read: the chat may have changed (or been deleted) meanwhile
    msg.meta = {**(msg.meta or {}), "verification": result}
    db.commit()
    return result
