import logging
import os
from dotenv import load_dotenv


class Config:
    def __init__(self) -> None:
        logging.debug("Loading configuration...")
        load_dotenv()
        self.changelog_url = os.getenv(
            "CHANGELOG_URL",
            "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md",
        )
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.poll_interval = int(os.getenv("POLL_INTERVAL", "600"))  # seconds
        self.database_path = os.getenv("DATABASE_PATH", "data/bot.db")
        
        logging.debug(f"Loaded config: token={'***' if self.telegram_token else 'MISSING'}, chat_id={self.telegram_chat_id}, poll_interval={self.poll_interval}")

    def validate(self) -> None:
        missing = []
        if not self.telegram_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.telegram_chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        if missing:
            logging.error(f"Missing required environment variables: {', '.join(missing)}")
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )
        logging.debug("Configuration validation passed")

