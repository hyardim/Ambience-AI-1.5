from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class DatabaseConfig:
    host: str = os.getenv("POSTGRES_HOST", "localhost")
    port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    user: str = os.getenv("POSTGRES_USER", "admin")
    password: str = os.getenv("POSTGRES_PASSWORD", "")
    database: str = os.getenv("POSTGRES_DB", "ambience_knowledge")
    
    @property
    def connection_string(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

@dataclass
class EmbeddingConfig:
    model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "1536"))

@dataclass
class ChunkingConfig:
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "500"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "50"))

@dataclass
class PathConfig:
    root: Path = Path(__file__).parent.parent
    data_raw: Path = root / "data" / "raw"
    data_processed: Path = root / "data" / "processed"
    logs: Path = root / "logs"

db_config = DatabaseConfig()
embed_config = EmbeddingConfig()
chunk_config = ChunkingConfig()
path_config = PathConfig()