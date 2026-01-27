from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_chat_id: int
    manager_username: str

def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is empty. Set it in Railway Variables or .env")

    admin_chat_id = int(os.getenv("ADMIN_CHAT_ID", "0"))
    if admin_chat_id == 0:
        raise RuntimeError("ADMIN_CHAT_ID is empty. Set your numeric Telegram ID")

    manager_username = os.getenv("MANAGER_USERNAME", "").strip().lstrip("@")
    if not manager_username:
        raise RuntimeError("MANAGER_USERNAME is empty. Set your Telegram username")

    return Config(
        bot_token=token,
        admin_chat_id=admin_chat_id,
        manager_username=manager_username
    )
