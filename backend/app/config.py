import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = os.getenv("APP_NAME", "TrustShield")
    app_version: str = os.getenv("APP_VERSION", "1.0.0")
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # API
    api_key: str = os.getenv("API_KEY", "")
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")

    # Database
    database_url: str = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/trustshield")

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Neo4j
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "password")

    # Kafka
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

    # ML Model
    muril_model_path: str = os.getenv("MURIL_MODEL_PATH", "trustshield/backend/ml/artifacts/muril_scam_classifier/model.onnx")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_format: str = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")


# Global settings instance
settings = Settings()

# Database URL for SQLAlchemy
DATABASE_URL = settings.database_url

# Redis URL for Celery
REDIS_URL = settings.redis_url

# Neo4j connection details
NEO4J_URI = settings.neo4j_uri
NEO4J_USER = settings.neo4j_user
NEO4J_PASSWORD = settings.neo4j_password

# Kafka connection
KAFKA_BOOTSTRAP_SERVERS = settings.kafka_bootstrap_servers
