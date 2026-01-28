import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from config import load_config
import texts
import keyboards as kb
import db
from states import FreeTestFlow, LuxFlow
from services import make_test_report


def is_int(s: str) -> bool:
    try:
        int(s)
        return True
    except Exception:
        return False


def safe_username(u: str | None) -> str:
    if not u:
        return "—"
    return f"@{u}"


def safe_text(m: Message) -> str | None:
    if not m.text:
        return None
    t = m.text.strip()
    return t if t else None


async def main():
    logging.basicConfig(level=logging.INFO)

    cfg = load_config()
    db.init_db()

    bot = Bot(token=cfg.bot_token, parse_mode=ParseMode.MARKDOWN)
    dp = Dispatcher()

    async def notify_admin(text: str):
        """
        Admin notifications: WITHOUT Markdown parsing (parse_mode=None),
        so Telegram will not fail on special symbols.
        """
        try:
            await bot.send_message(
                cfg.admin_chat_id,
                text,
                parse_mode=None,
                disable_web_page_preview=True,
            )
            logging.info("Admin notified OK")
        except Exception as e:
            logging.exception(f"Admin notify error: {e}")

    @dp.error()
    async def on_error(event, exception: Exception):
        logging.exception(f"Unhandled error: {exception}")
        return True

    # /start
    @dp.message(CommandStart())
    async def start(m: Message, state: FSMContext):
        await state.clear()
        db.upsert_user(m.from_user.id, m.from_user.username)
        await m.answer(texts.START, reply_markup=kb.main_menu(cfg.manager_username))

    # back menu
    @dp.callback_query(F.data == "back:menu")
    async def back_menu(c: CallbackQuery, state: FSMContext):
        await state.clear()
        await c.message.edit_text(texts.START, reply_markup=kb.main_menu(cfg.manager_username))
        await c.answer()

    # ========================= PREMIUM =========================

    @dp.callback_query(F.data == "premium:page")
    async def premium_page(c: CallbackQuery):
        await c.message.answer(texts.PREMIUM_PAGE, reply_markup=kb.premium_kb(cfg.manager_username))
        await c.answer()

    @dp.callback_query(F.data == "premium:buy")
    async def premium_buy(c: CallbackQuery):
        db.set_subscription(c.from_user.id, plan="premium", status="pending")

        last = db.get_last_test_fields(c.from_user.id)

        await notify_admin(
            "🟦 Premium запрос\n"
            f"User: {safe_username(c.from_user.username)} | id={c.from_user.id}\n"
            f"Niche: {last.get('niche','—')}\n"
            f"TikTok: {last.get('tiktok_link','—')}\n"
            f"Goal: {last.get('goal','—')}\n"
            "Status: pending\n"
            "Action: свяжись лично и договорись об оплате/старте."
        )

        await c.message.answer(texts.MANAGER_INSTRUCTION, reply_markup=kb.manager_only_kb(cfg.manager_username))
        await c.message.answer(texts.PREMIUM_REQUEST_SENT, reply_markup=kb.manager_only_kb(cfg.manager_username))
        await c.answer()

    # ========================= LUX =========================

    @dp.callback_query(F.data == "lux:page")
    async def lux_page(c: CallbackQuery):
        await c.message.answer(texts.LUX_PAGE, reply_markup=kb.lux_kb(cfg.manager_username))
        await c.answer()

    @dp.callback_query(F.data == "lux:request")
    async def lux_request(c: CallbackQuery, state: FSMContext):
        await state.set_state(LuxFlow.goal)
        await c.message.answer("Lux: какая цель? (заявки / продажи / бренд)")
        await c.answer()

    @dp.message(LuxFlow.goal)
    async def lux_goal(m: Message, state: FSMContext):
        txt = safe_text(m)
        if not txt:
            return await m.answer("Напиши цель *текстом* (заявки / продажи / бренд).")
        await state.update_data(goal=txt)
        await state.set_state(LuxFlow.volume)
        await m.answer("Сколько роликов в месяц? (10 / 20 / 30)")

    @dp.message(LuxFlow.volume)
    async def lux_volume(m: Message, state: FSMContext):
        txt = safe_text(m)
        if not txt or txt not in {"10", "20", "30"}:
            return await m.answer("Введи 10, 20 или 30.")
        await state.update_data(volume=int(txt))
        await state.set_state(LuxFlow.account_link)
        await m.answer("Ссылка на TikTok аккаунт (текстом):")

    @dp.message(LuxFlow.account_link)
    async def lux_account(m: Message, state: FSMContext):
        link = safe_text(m)
        if not link:
            return await m.answer("Пришли ссылку *текстом* (не файлом/стикером).")

        data = await state.get_data()
        goal = data.get("goal")
        volume = data.get("volume")
        await state.clear()

        db.set_subscription(m.from_user.id, plan="lux", status="pending")

        last = db.get_last_test_fields(m.from_user.id)

        await notify_admin(
            "👑 Lux запрос\n"
            f"User: {safe_username(m.from_user.username)} | id={m.from_user.id}\n"
            f"Goal: {goal}\n"
            f"Volume: {volume}/мес\n"
            f"Account: {link}\n"
            f"Niche(from last): {last.get('niche','—')}\n"
            f"TikTok(from last): {last.get('tiktok_link','—')}\n"
            "Status: pending\n"
            "Action: свяжись лично и уточни детали/цену."
        )

        await m.answer(texts.MANAGER_INSTRUCTION, reply_markup=kb.manager_only_kb(cfg.manager_username))
        await m.answer(texts.LUX_REQUEST_SENT, reply_markup=kb.manager_only_kb(cfg.manager_username))
        await m.answer("🔙 Меню", reply_markup=kb.main_menu(cfg.manager_username))

    # ========================= FREE TEST =========================

    @dp.callback_query(F.data == "free:start")
    async def free_start(c: CallbackQuery):
        await c.message.answer(texts.FREE_INTRO, reply_markup=kb.free_intro_kb(cfg.manager_username))
        await c.answer()

    @dp.callback_query(F.data == "free:begin")
    async def free_begin(c: CallbackQuery, state: FSMContext):
        db.start_free_test(c.from_user.id)
        await state.set_state(FreeTestFlow.niche)
        await c.message.answer("Выбери нишу:", reply_markup=kb.niche_kb())
        await c.answer()

    @dp.callback_query(F.data.startswith("free:niche:"))
    async def free_niche(c: CallbackQuery, state: FSMContext):
        niche = c.data.split("free:niche:", 1)[1]
        db.update_test_field(c.from_user.id, "niche", niche)
        await state.set_state(FreeTestFlow.tiktok_link)
        await c.message.answer("Ссылка на TikTok аккаунт (текстом):")
        await c.answer()

    @dp.message(FreeTestFlow.tiktok_link)
    async def free_link(m: Message, state: FSMContext):
        link = safe_text(m)
        if not link:
            return await m.answer("Пришли ссылку *текстом* (не файлом/стикером/голосом).")
        db.update_test_field(m.from_user.id, "tiktok_link", link)
        await state.set_state(FreeTestFlow.goal)
        await m.answer(
            "Цель теста:\n"
            "✅ выбери кнопкой *или* напиши текстом одним сообщением.",
            reply_markup=kb.goal_kb(),
        )

    # ✅ ТЕКСТОВЫЙ ВВОД ЦЕЛИ (must-have)
    @dp.message(FreeTestFlow.goal)
    async def free_goal_text(m: Message, state: FSMContext):
        txt = safe_text(m)
        if not txt:
            return await m.answer("Напиши цель теста *текстом* одним сообщением.")
        db.update_test_field(m.from_user.id, "goal", txt)
        await state.set_state(FreeTestFlow.material)
        await m.answer(
            "Отправь исходник:\n"
            "1) 🎥 *видео файлом*\n"
            "или\n"
            "2) 🔗 *ссылку текстом* одним сообщением."
        )

    @dp.callback_query(F.data.startswith("free:goal:"))
    async def free_goal_btn(c: CallbackQuery, state: FSMContext):
        goal = c.data.split("free:goal:", 1)[1]
        db.update_test_field(c.from_user.id, "goal", goal)
        await state.set_state(FreeTestFlow.material)
        await c.message.answer(
            "Отправь исходник:\n"
            "1) 🎥 *видео файлом*\n"
            "или\n"
            "2) 🔗 *ссылку текстом* одним сообщением."
        )
        await c.answer()

    # ✅ FIX: материал принимает ТОЛЬКО video или text-link, остальное отклоняет понятным сообщением
    @dp.message(FreeTestFlow.material)
    async def free_material(m: Message, state: FSMContext):
        # 1) Видео файлом
        if m.video:
            db.update_test_field(m.from_user.id, "material_type", "video")
            db.update_test_field(m.from_user.id, "material_value", m.video.file_id)

        # 2) Ссылка текстом
        elif m.text and m.text.strip():
            link = m.text.strip()
            db.update_test_field(m.from_user.id, "material_type", "link")
            db.update_test_field(m.from_user.id, "material_value", link)

        # 3) Фото/HEIC/документ/аудио/голос/стикер и т.п.
        else:
            return await m.answer(
                "❌ Сейчас пришло не видео и не ссылка.\n\n"
                "Пришли:\n"
                "1️⃣ 🎥 видео *файлом* (📎 → Видео)\n"
                "или\n"
                "2️⃣ 🔗 ссылку *текстом* одним сообщением."
            )

        db.set_test_day(m.from_user.id, 1)
        await state.clear()

        await m.answer(
            "✅ Принято. *День 1* стартовал.\n"
            "Видео №1 — тестируем хук и удержание.\n"
            "Выложи в течение 24 часов.",
            reply_markup=kb.day_actions_kb()
        )

    # ========================= FALLBACK =========================
    # Если пользователь прислал что-то не то в процессе FSM — не молчим
    @dp.message(FSMContext)
    async def fsm_fallback(m: Message):
        await m.answer(
            "Я жду ответ *текстом* или *видео файлом* по текущему шагу.\n"
            "Если нужно — нажми /start."
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
