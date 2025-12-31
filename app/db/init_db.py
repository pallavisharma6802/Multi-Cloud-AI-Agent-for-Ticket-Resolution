from app.db.models import Base
from app.db.session import engine
from app.config import settings
import logging

logger = logging.getLogger(__name__)


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=settings.log_level)
    init_db()
