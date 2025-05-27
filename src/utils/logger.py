import logging
from src.config import settings

def setup_logging(name: str = None) -> logging.Logger:
    if not logging.getLogger().hasHandlers():
        log_level = logging.DEBUG if settings.DEBUG_MODE else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    return logging.getLogger(name if name else __name__)