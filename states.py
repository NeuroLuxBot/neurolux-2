from aiogram.fsm.state import State, StatesGroup

class FreeTestFlow(StatesGroup):
    niche = State()
    tiktok_link = State()
    goal = State()
    material = State()

    day_publish_link = State()
    stats_views = State()
    stats_likes = State()
    stats_comments = State()
    stats_follows = State()

class LuxFlow(StatesGroup):
    goal = State()
    volume = State()
    account_link = State()
