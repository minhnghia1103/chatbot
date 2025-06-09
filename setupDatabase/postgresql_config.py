from dataclasses import dataclass
from typing import Optional, Dict, Any
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class PostgreSQLConfig:
    """PostgreSQL database configuration settings."""

    host: str
    port: int
    database: str
    user: str  # Changed from username to user
    password: str
    schema_path: Optional[str] = None
    csv_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'host': self.host,
            'port': self.port,
            'database': self.database,
            'user': self.user,  # PostgreSQL connection expects 'user', not 'username'
            'password': self.password
        }


# Default PostgreSQL configuration
DEFAULT_POSTGRESQL_CONFIG = PostgreSQLConfig(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    database=os.getenv("POSTGRES_DB", "project2"),
    user=os.getenv("POSTGRES_USER", "minhnghia"),  # Changed from username to user
    password=os.getenv("POSTGRES_PASSWORD", "minhnghia"),
    schema_path="postgresql_schemas.sql",
    csv_path="E:\\llm\\llm_engineering\\project2\\crawlData\\product_details.csv"
)
