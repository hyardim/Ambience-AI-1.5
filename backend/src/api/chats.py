from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from src.db.session import get_db
from src.db.models import User, Chat, Message
from src.schemas.chat import ChatCreate, ChatResponse
from src.core.security import get_current_user

router = APIRouter()
@router.post("/", response_model=ChatResponse)
def create_chat(
    chat_data: ChatCreate, 
    db: Session = Depends(get_db),
    current_user_email: str = Depends(get_current_user)
):
    """
    Creates a new conversation for the currently logged-in user.
    """
    # 1. Find the User in the DB (based on the token email)
    user = db.query(User).filter(User.email == current_user_email).first()
    if not user:
        # If "Dr. Test" isn't in the DB, create him on the fly (Dev Convenience)
        user = User(email=current_user_email, hashed_password="dev_placeholder", full_name="Dr. Test")
        db.add(user)
        db.commit()
        db.refresh(user)

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
    current_user_email: str = Depends(get_current_user)
):
    """
    Returns a list of all conversations for the current user.
    """
    # 1. Find User
    user = db.query(User).filter(User.email == current_user_email).first()
    if not user:
        return [] # User exists in token but not DB? Return empty list.

    # 2. Get their Chats
    chats = db.query(Chat).filter(Chat.user_id == user.id)\
        .order_by(Chat.created_at.desc())\
        .offset(skip).limit(limit).all()
        
    return chats

@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user_email: str = Depends(get_current_user)
):
    """
    Deletes a specific conversation.
    """
    user = db.query(User).filter(User.email == current_user_email).first()
    
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    db.delete(chat)
    db.commit()
    return None