from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from src.db.session import get_db
from src.db.models import Chat, Message, User, ChatStatus
from src.core import security

router = APIRouter()

# --- Pydantic Schemas (Validation) ---
class ChatCreate(BaseModel):
    title: str = "New Chat"

class MessageCreate(BaseModel):
    content: str

class ChatResponse(BaseModel):
    id: int
    title: str
    status: ChatStatus
    created_at: str
    
    # We use a custom config to allow reading from ORM objects
    class Config:
        from_attributes = True

# --- Helper: Get Current User Object ---
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
    """
    Create a new chat linked to the logged-in user.
    """
    new_chat = Chat(
        title=chat_data.title,
        user_id=current_user.id,  # <--- LINKING THE USER HERE
        status=ChatStatus.OPEN
    )
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)
    
    # Convert datetime to string for Pydantic (simple fix)
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
    """
    List only the chats that belong to the logged-in user.
    """
    chats = db.query(Chat).filter(Chat.user_id == current_user.id).all()
    
    # Convert for response
    results = []
    for c in chats:
        results.append(ChatResponse(
            id=c.id,
            title=c.title,
            status=c.status,
            created_at=c.created_at.isoformat()
        ))
    return results

@router.post("/{chat_id}/message")
def send_message(
    chat_id: int,
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj)
):
    """
    Send a message to a specific chat.
    Ensures the user owns the chat.
    """
    # 1. Find the chat AND ensure user owns it
    chat = db.query(Chat).filter(
        Chat.id == chat_id, 
        Chat.user_id == current_user.id
    ).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # 2. Save User Message
    user_msg = Message(
        content=message.content,
        sender="user",
        chat_id=chat.id
    )
    db.add(user_msg)
    
    # 3. (Placeholder) AI Response
    ai_msg = Message(
        content=f"I received your message: {message.content}",
        sender="ai",
        chat_id=chat.id
    )
    db.add(ai_msg)
    
    db.commit()
    return {"status": "Message sent", "ai_response": ai_msg.content}