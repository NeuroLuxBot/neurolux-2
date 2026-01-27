from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

PORTFOLIO_URL = "https://t.me/neurolux2025"

def manager_url(username: str) -> str:
    return f"https://t.me/{username}"

def main_menu(manager_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Бесплатный 3-дневный тест", callback_data="free:start")],
        [InlineKeyboardButton(text="💎 Premium — основной тариф", callback_data="premium:page")],
        [InlineKeyboardButton(text="👑 Lux — апгрейд", callback_data="lux:page")],
        [InlineKeyboardButton(text="📂 Портфолио / Кейсы", url=PORTFOLIO_URL)],
        [InlineKeyboardButton(text="👨‍💼 Менеджер", url=manager_url(manager_username))],
    ])

def free_intro_kb(manager_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Начать тест", callback_data="free:begin")],
        [InlineKeyboardButton(text="👨‍💼 Менеджер", url=manager_url(manager_username))],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back:menu")],
    ])

def niche_kb() -> InlineKeyboardMarkup:
    opts = ["Эксперт", "Бизнес", "Товарка", "Блог", "Другое"]
    rows = [[InlineKeyboardButton(text=o, callback_data=f"free:niche:{o}")] for o in opts]
    rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def goal_kb() -> InlineKeyboardMarkup:
    opts = ["Просмотры", "Подписчики", "Заявки"]
    rows = [[InlineKeyboardButton(text=o, callback_data=f"free:goal:{o}")] for o in opts]
    rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def day_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я выложил (ввести ссылку)", callback_data="free:posted")],
        [InlineKeyboardButton(text="❓ Как правильно выложить?", callback_data="free:rules")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back:menu")],
    ])

def after_posted_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Ввести статистику", callback_data="free:stats")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back:menu")],
    ])

def after_test_kb(manager_username: str) -> InlineKeyboardMarkup:
    """
    ВАЖНО:
    Premium = главный путь (единственная основная CTA).
    Lux = апгрейд по желанию (вторичная опция).
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Продолжить в Premium (3990 ₸)", callback_data="premium:buy")],
        [InlineKeyboardButton(text="👑 Апгрейд Lux (по желанию)", callback_data="lux:page")],
        [InlineKeyboardButton(text="👨‍💼 Менеджер", url=manager_url(manager_username))],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back:menu")],
    ])

def premium_kb(manager_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Запросить подключение Premium", callback_data="premium:buy")],
        [InlineKeyboardButton(text="👨‍💼 Менеджер", url=manager_url(manager_username))],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back:menu")],
    ])

def lux_kb(manager_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Запросить Lux (анкета)", callback_data="lux:request")],
        [InlineKeyboardButton(text="👨‍💼 Менеджер", url=manager_url(manager_username))],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back:menu")],
    ])

def manager_only_kb(manager_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💼 Менеджер", url=manager_url(manager_username))],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back:menu")],
    ])
