from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from src.db.session import get_db
from src.db.models import User, Chat, Message
from src.schemas.chat import ChatCreate, ChatResponse, MessageCreate, MessageResponse
from src.core.security import get_current_user

router = APIRouter()


def _get_user_by_email_or_404(db: Session, email: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/", response_model=ChatResponse)
def create_chat(
    chat_data: ChatCreate, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Creates a new conversation for the currently logged-in user.
    """
    # 1. Find the User in the DB (based on the token email)
    user = _get_user_by_email_or_404(db, current_user["email"])

    # 2. Create the Chat
    new_chat = Chat(
        user_id=user.id,
        title=chat_data.title or "New Consultation" # Default title
    )
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)
    
    return new_chat

@router.get("/", response_model=List[ChatResponse])
def get_chats(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Returns a list of all conversations for the current user.
    """
    # 1. Find User
    user = _get_user_by_email_or_404(db, current_user["email"])

    # 2. Get their Chats
    chats = db.query(Chat).filter(Chat.user_id == user.id)\
        .order_by(Chat.created_at.desc())\
        .offset(skip).limit(limit).all()
        
    return chats


@router.get("/{chat_id}", response_model=ChatResponse)
def get_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Returns a single conversation for the current user.
    """
    user = _get_user_by_email_or_404(db, current_user["email"])
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat

@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Deletes a specific conversation.
    """
    user = _get_user_by_email_or_404(db, current_user["email"])
    
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    db.delete(chat)
    db.commit()
    return None

@router.post("/{chat_id}/message", response_model=MessageResponse)
def send_message(
    chat_id: int,
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Saves user message and returns a Mock AI response.
    """
    # 1. Validate User owns the chat
    user = _get_user_by_email_or_404(db, current_user["email"])
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # 2. Save User Message to DB
    user_msg = Message(
        chat_id=chat.id, 
        role="user", 
        content=message.content
    )
    db.add(user_msg)
    db.commit()
    
    # 3. Generate Mock Response (We will hook up RAG here later)
    ai_content = f"I received: '{message.content}'. (RAG Brain coming soon!)"
    
    ai_msg = Message(
        chat_id=chat.id, 
        role="assistant", 
        content=ai_content
    )
    db.add(ai_msg)
    db.commit()
    db.refresh(ai_msg)
    
    return ai_msg