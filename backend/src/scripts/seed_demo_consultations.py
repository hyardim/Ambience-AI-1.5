from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import Any

# Make script runnable as:
#   python backend/src/scripts/seed_demo_consultations.py
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.core.security import get_password_hash
from src.db.models import Chat, ChatStatus, Message, User, UserRole
from src.db.session import SessionLocal


DEMO_PREFIX = "[DEMO]"
DEFAULT_PASSWORD = "password123"


@dataclass(frozen=True)
class DemoUser:
    email: str
    full_name: str
    role: UserRole
    specialty: str | None = None


@dataclass(frozen=True)
class DemoMessage:
    sender: str
    content: str
    citations: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class DemoConsultation:
    key: str
    title: str
    gp_email: str
    specialist_email: str | None
    specialty: str
    severity: str
    status: ChatStatus
    patient_context: dict[str, Any]
    review_feedback: str | None
    messages: list[DemoMessage]


DEMO_USERS: list[DemoUser] = [
    DemoUser(
        email="gp@example.com",
        full_name="Dr. GP User",
        role=UserRole.GP,
    ),
]


DEMO_CONSULTATIONS: list[DemoConsultation] = [
    DemoConsultation(
        key="neurology-ms-relapse",
        title=f"{DEMO_PREFIX} Neurology A&G: probable MS relapse while on fingolimod",
        gp_email="gp@example.com",
        specialist_email=None,
        specialty="neurology",
        severity="urgent",
        status=ChatStatus.SUBMITTED,
        patient_context={
            "age": 34,
            "sex": "female",
            "history": ["relapsing-remitting MS", "migraine"],
            "current_medication": ["fingolimod", "vitamin D"],
            "symptom_duration_days": 5,
            "red_flags": ["new unilateral leg weakness", "gait instability"],
        },
        review_feedback=None,
        messages=[
            DemoMessage(
                sender="user",
                content=(
                    "34F with RRMS on fingolimod has 5 days of new left leg weakness and sensory change. "
                    "No fever, no urinary symptoms, obs stable. Please advise if this should be managed as a relapse "
                    "and whether steroids can be started in primary care while awaiting urgent neuro review."
                ),
            ),
            DemoMessage(
                sender="ai",
                content=(
                    "Features are concerning for true relapse rather than pseudo-relapse. Suggested next steps: "
                    "exclude infection with urinalysis/FBC/CRP, arrange urgent MRI brain/spine, and discuss oral "
                    "methylprednisolone 500 mg daily for 5 days with neurology if no contraindications."
                ),
                citations=[
                    {"source": "NICE NG220", "section": "Multiple sclerosis relapses"},
                    {"source": "ABN MS guidance", "section": "Acute relapse management"},
                ],
            ),
        ],
    ),
    DemoConsultation(
        key="rheumatology-inflammatory-arthritis",
        title=f"{DEMO_PREFIX} Rheumatology A&G: persistent small-joint inflammatory arthritis",
        gp_email="gp@example.com",
        specialist_email=None,
        specialty="rheumatology",
        severity="routine",
        status=ChatStatus.SUBMITTED,
        patient_context={
            "age": 52,
            "sex": "female",
            "history": ["hypertension"],
            "symptoms_weeks": 11,
            "exam": ["bilateral MCP tenderness", "early morning stiffness >60 min"],
            "bloods": {"RF": "positive", "anti_CCP": "strong positive", "CRP_mg_per_L": 22},
        },
        review_feedback=None,
        messages=[
            DemoMessage(
                sender="user",
                content=(
                    "52F with 11 weeks symmetrical hand/wrist pain and morning stiffness >1 hour. RF and anti-CCP "
                    "positive, CRP 22. No systemic red flags. Should we start bridging prednisolone in primary care "
                    "before first rheumatology appointment?"
                ),
            ),
            DemoMessage(
                sender="ai",
                content=(
                    "Likely early rheumatoid arthritis. Recommend urgent early inflammatory arthritis pathway referral, "
                    "baseline bloods (FBC/U&E/LFT/HBV/HCV), and consider short prednisolone bridge only after specialist "
                    "advice due to masking disease activity and comorbidity risk."
                ),
                citations=[
                    {"source": "NICE NG100", "section": "Rheumatoid arthritis in adults"},
                ],
            ),
        ],
    ),
    DemoConsultation(
        key="neurology-headache-red-flags",
        title=f"{DEMO_PREFIX} Neurology A&G: recurrent headache with visual aura and transient confusion",
        gp_email="gp@example.com",
        specialist_email=None,
        specialty="neurology",
        severity="urgent",
        status=ChatStatus.SUBMITTED,
        patient_context={
            "age": 41,
            "sex": "male",
            "history": ["migraine with aura"],
            "current_pattern": "increasing frequency over 6 weeks",
            "recent_events": ["2 episodes transient disorientation (~20 min)", "one nocturnal headache"],
            "neuro_exam_in_surgery": "no focal deficit",
        },
        review_feedback=None,
        messages=[
            DemoMessage(
                sender="user",
                content=(
                    "41M known migraine now has more frequent headaches with aura and two episodes of transient "
                    "confusion in the last month. No persistent focal deficits. Should this be expedited imaging or "
                    "urgent clinic review?"
                ),
            ),
            DemoMessage(
                sender="ai",
                content=(
                    "Given change in headache pattern plus transient cognitive symptoms, treat as urgent secondary "
                    "headache exclusion. Recommend urgent MRI brain with contrast and specialist review within 2 weeks; "
                    "advise immediate ED attendance if prolonged confusion, new neuro deficits, or thunderclap onset."
                ),
                citations=[
                    {"source": "NICE NG127", "section": "Headaches in over 12s"},
                    {"source": "SIGN headache guideline", "section": "Red-flag symptoms"},
                ],
            ),
        ],
    ),
]


def get_or_create_user(db, demo_user: DemoUser) -> tuple[User, bool]:
    user = db.query(User).filter(User.email == demo_user.email).first()
    created = False

    if user is None:
        user = User(
            email=demo_user.email,
            full_name=demo_user.full_name,
            role=demo_user.role,
            specialty=demo_user.specialty,
            hashed_password=get_password_hash(DEFAULT_PASSWORD),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        created = True
    else:
        changed = False
        if user.full_name != demo_user.full_name:
            user.full_name = demo_user.full_name
            changed = True
        if user.role != demo_user.role:
            user.role = demo_user.role
            changed = True
        if user.specialty != demo_user.specialty:
            user.specialty = demo_user.specialty
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if changed:
            db.commit()
            db.refresh(user)

    return user, created


def delete_existing_demo_chats(db) -> int:
    chats = db.query(Chat).filter(Chat.title.like(f"{DEMO_PREFIX}%")).all()
    count = len(chats)
    for chat in chats:
        db.delete(chat)
    if count:
        db.commit()
    return count


def upsert_consultation(db, consultation: DemoConsultation, users_by_email: dict[str, User], base_time: datetime) -> tuple[Chat, bool]:
    owner = users_by_email[consultation.gp_email]
    specialist = users_by_email.get(consultation.specialist_email) if consultation.specialist_email else None

    chat = (
        db.query(Chat)
        .filter(Chat.title == consultation.title, Chat.user_id == owner.id)
        .first()
    )

    created = False
    if chat is None:
        chat = Chat(title=consultation.title, user_id=owner.id)
        db.add(chat)
        db.flush()
        created = True

    created_at = base_time
    assigned_at = created_at + timedelta(minutes=10) if specialist else None
    reviewed_at = assigned_at + timedelta(minutes=20) if consultation.status in {ChatStatus.APPROVED, ChatStatus.REJECTED} else None

    chat.status = consultation.status
    chat.specialty = consultation.specialty
    chat.severity = consultation.severity
    chat.patient_context = consultation.patient_context
    chat.specialist_id = specialist.id if specialist else None
    chat.assigned_at = assigned_at if consultation.status in {ChatStatus.ASSIGNED, ChatStatus.REVIEWING, ChatStatus.APPROVED, ChatStatus.REJECTED} else None
    chat.reviewed_at = reviewed_at
    chat.review_feedback = consultation.review_feedback
    chat.created_at = created_at

    db.query(Message).filter(Message.chat_id == chat.id).delete(synchronize_session=False)

    for index, demo_msg in enumerate(consultation.messages):
        msg_time = created_at + timedelta(minutes=index + 1)
        db.add(
            Message(
                chat_id=chat.id,
                sender=demo_msg.sender,
                content=demo_msg.content,
                citations=demo_msg.citations,
                created_at=msg_time,
            )
        )

    chat.updated_at = created_at + timedelta(minutes=max(len(consultation.messages), 1) + 1)
    db.commit()
    db.refresh(chat)
    return chat, created


def seed_demo_data(reset_demo_chats: bool) -> None:
    db = SessionLocal()
    try:
        created_users = 0
        users_by_email: dict[str, User] = {}

        for demo_user in DEMO_USERS:
            user, was_created = get_or_create_user(db, demo_user)
            users_by_email[demo_user.email] = user
            created_users += int(was_created)

        deleted_chats = delete_existing_demo_chats(db) if reset_demo_chats else 0

        created_chats = 0
        updated_chats = 0

        now = datetime.utcnow()
        for index, consultation in enumerate(DEMO_CONSULTATIONS):
            chat_base_time = now - timedelta(days=(len(DEMO_CONSULTATIONS) - index) * 2)
            _, was_created = upsert_consultation(
                db=db,
                consultation=consultation,
                users_by_email=users_by_email,
                base_time=chat_base_time,
            )
            if was_created:
                created_chats += 1
            else:
                updated_chats += 1

        print("Demo consultation seeding complete.")
        print(f"Users created: {created_users}")
        print(f"Demo chats deleted via --reset: {deleted_chats}")
        print(f"Chats created: {created_chats}")
        print(f"Chats updated: {updated_chats}")
        print(f"Default password for created demo users: {DEFAULT_PASSWORD}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed realistic demo GP→specialist consultations into the Ambience backend database."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing chats with titles starting '[DEMO]' before seeding.",
    )
    args = parser.parse_args()

    seed_demo_data(reset_demo_chats=args.reset)


if __name__ == "__main__":
    main()
