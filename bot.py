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
        try:
            await bot.send_message(
                cfg.admin_chat_id,
                text,
                parse_mode=None,
                disable_web_page_preview=True
            )
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
            f"User: {safe_username(c.from_user.username)} | {c.from_user.id}\n"
            f"Niche: {last.get('niche','—')}\n"
            f"TikTok: {last.get('tiktok_link','—')}\n"
            f"Goal: {last.get('goal','—')}"
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
        await c.message.answer("Lux: какая цель?")
        await c.answer()

    @dp.message(LuxFlow.goal)
    async def lux_goal(m: Message, state: FSMContext):
        txt = safe_text(m)
        if not txt:
            return await m.answer("Напиши цель текстом.")
        await state.update_data(goal=txt)
        await state.set_state(LuxFlow.volume)
        await m.answer("Сколько роликов в месяц? (10 / 20 / 30)")

    @dp.message(LuxFlow.volume)
    async def lux_volume(m: Message, state: FSMContext):
        txt = safe_text(m)
        if txt not in {"10", "20", "30"}:
            return await m.answer("Введи 10, 20 или 30.")
        await state.update_data(volume=int(txt))
        await state.set_state(LuxFlow.account_link)
        await m.answer("Ссылка на TikTok аккаунт:")

    @dp.message(LuxFlow.account_link)
    async def lux_account(m: Message, state: FSMContext):
        link = safe_text(m)
        if not link:
            return await m.answer("Пришли ссылку текстом.")

        data = await state.get_data()
        await state.clear()

        db.set_subscription(m.from_user.id, plan="lux", status="pending")

        await notify_admin(
            "👑 Lux запрос\n"
            f"User: {safe_username(m.from_user.username)} | {m.from_user.id}\n"
            f"Goal: {data.get('goal')}\n"
            f"Volume: {data.get('volume')}\n"
            f"Account: {link}"
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
        await c.message.answer("Ссылка на TikTok аккаунт:")
        await c.answer()

    @dp.message(FreeTestFlow.tiktok_link)
    async def free_link(m: Message, state: FSMContext):
        link = safe_text(m)
        if not link:
            return await m.answer("Пришли ссылку текстом.")
        db.update_test_field(m.from_user.id, "tiktok_link", link)
        await state.set_state(FreeTestFlow.goal)
        await m.answer("Цель теста:", reply_markup=kb.goal_kb())

    # 🔥 ВАЖНО: ТЕКСТОВЫЙ ВВОД ЦЕЛИ
    @dp.message(FreeTestFlow.goal)
    async def free_goal_text(m: Message, state: FSMContext):
        txt = safe_text(m)
        if not txt:
            return await m.answer("Напиши цель теста текстом.")

        db.update_test_field(m.from_user.id, "goal", txt)
        await state.set_state(FreeTestFlow.material)

        await m.answer(
            "Отправь исходник:\n"
            "1) видео файлом\n"
            "или\n"
            "2) ссылку текстом"
        )

    @dp.callback_query(F.data.startswith("free:goal:"))
    async def free_goal_btn(c: CallbackQuery, state: FSMContext):
        goal = c.data.split("free:goal:", 1)[1]
        db.update_test_field(c.from_user.id, "goal", goal)
        await state.set_state(FreeTestFlow.material)
        await c.message.answer("Отправь исходник.")
        await c.answer()

    # ========================= FALLBACK =========================

    @dp.message(FSMContext)
    async def fsm_fallback(m: Message):
        await m.answer(
            "Я жду ответ текстом или видео.\n"
            "Если запутался — нажми /start."
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
