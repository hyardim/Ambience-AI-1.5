import os

class Settings:
    PROJECT_NAME: str = "Ambience AI"
    PROJECT_VERSION: str = "1.5.0"
    
    # Security
    # In production, we would pull this from os.getenv("SECRET_KEY")
    SECRET_KEY: str = "TEST_SECRET_KEY_DO_NOT_USE_IN_PROD" 
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days

settings = Settings()