from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Any
from pydantic import BaseModel
from src.db.session import get_db
from src.db.models import Chat, Message, User, ChatStatus, AuditLog
from src.core import security

router = APIRouter()

# --- Pydantic Schemas ---
class ChatCreate(BaseModel):
    title: str = "New Chat"

class MessageCreate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    id: int
    content: str
    sender: str
    created_at: str
    citations: Optional[List[Any]] = None

class ChatResponse(BaseModel):
    id: int
    title: str
    status: ChatStatus
    created_at: str

class ChatWithMessages(ChatResponse):
    messages: List[MessageResponse] = []

# --- Helper ---
def get_current_user_obj(
    db: Session = Depends(get_db),
    email: str = Depends(security.get_current_user)
) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# --- Endpoints ---

@router.post("/", response_model=ChatResponse)
def create_chat(
    chat_data: ChatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj)
):
    new_chat = Chat(
        title=chat_data.title,
        user_id=current_user.id,
        status=ChatStatus.OPEN
    )
    db.add(new_chat)
    
    # Audit Log
    audit = AuditLog(
        user_id=current_user.id,
        action="CREATE_CHAT",
        details=f"Created chat: {new_chat.title}"
    )
    db.add(audit)
    
    db.commit()
    db.refresh(new_chat)
    
    return ChatResponse(
        id=new_chat.id,
        title=new_chat.title,
        status=new_chat.status,
        created_at=new_chat.created_at.isoformat()
    )

@router.get("/", response_model=List[ChatResponse])
def list_chats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj)
):
    chats = db.query(Chat).filter(Chat.user_id == current_user.id).all()
    return [
        ChatResponse(
            id=c.id,
            title=c.title,
            status=c.status,
            created_at=c.created_at.isoformat()
        ) for c in chats
    ]

@router.get("/{chat_id}", response_model=ChatWithMessages)
def get_chat_details(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj)
):
    chat = db.query(Chat).filter(
        Chat.id == chat_id, 
        Chat.user_id == current_user.id
    ).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Audit Log (Viewing)
    audit = AuditLog(
        user_id=current_user.id,
        action="VIEW_CHAT",
        details=f"Viewed chat ID: {chat_id}"
    )
    db.add(audit)
    db.commit()

    messages = db.query(Message).filter(Message.chat_id == chat.id).all()

    safe_messages = []
    for m in messages:
        created_str = m.created_at.isoformat() if m.created_at else ""
        safe_messages.append(MessageResponse(
            id=m.id,
            content=m.content,
            sender=m.sender,
            created_at=created_str,
            citations=m.citations
        ))

    return ChatWithMessages(
        id=chat.id,
        title=chat.title,
        status=chat.status,
        created_at=chat.created_at.isoformat() if chat.created_at else "",
        messages=safe_messages
    )

@router.post("/{chat_id}/message")
def send_message(
    chat_id: int,
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj)
):
    chat = db.query(Chat).filter(
        Chat.id == chat_id, 
        Chat.user_id == current_user.id
    ).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    user_msg = Message(content=message.content, sender="user", chat_id=chat.id)
    db.add(user_msg)
    
    # Placeholder for RAG citations (Empty list for now)
    ai_msg = Message(
        content=f"I received: {message.content}", 
        sender="ai", 
        chat_id=chat.id,
        citations=[] 
    )
    db.add(ai_msg)
    
    db.commit()
    return {"status": "Message sent", "ai_response": ai_msg.content}