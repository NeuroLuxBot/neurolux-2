import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, StateFilter
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
        # админу шлём без Markdown, чтобы не было "can't parse entities"
        try:
            await bot.send_message(
                cfg.admin_chat_id,
                text,
                parse_mode=None,
                disable_web_page_preview=True
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

        # УБРАЛИ texts.MANAGER_INSTRUCTION (дублирует и засоряет)
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
        await m.answer("Сколько роликов в месяц нужно? (10/20/30)")

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
            return await m.answer("Пришли ссылку на TikTok аккаунт *текстом* (не файлом/стикером).")

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

        # УБРАЛИ texts.MANAGER_INSTRUCTION (дублирует и засоряет)
        await m.answer(texts.LUX_REQUEST_SENT, reply_markup=kb.manager_only_kb(cfg.manager_username))
        await m.answer("🔙 Возврат в меню:", reply_markup=kb.main_menu(cfg.manager_username))

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
    async def free_tiktok_link(m: Message, state: FSMContext):
        link = safe_text(m)
        if not link:
            return await m.answer("Пришли ссылку на TikTok *текстом* (не файлом/стикером/голосом).")
        db.update_test_field(m.from_user.id, "tiktok_link", link)
        await state.set_state(FreeTestFlow.goal)
        await m.answer(
            "Цель теста:\n"
            "✅ выбери кнопкой *или* напиши текстом одним сообщением.",
            reply_markup=kb.goal_kb()
        )

    # Кнопка цели
    @dp.callback_query(F.data.startswith("free:goal:"))
    async def free_goal_btn(c: CallbackQuery, state: FSMContext):
        goal = c.data.split("free:goal:", 1)[1]
        db.update_test_field(c.from_user.id, "goal", goal)
        await state.set_state(FreeTestFlow.material)
        await c.message.answer(
            "Отправь исходник:\n"
            "1) *видео файлом* (лучше)\n"
            "или\n"
            "2) *ссылку текстом* одним сообщением."
        )
        await c.answer()

    # Текстовый ввод цели (must-have)
    @dp.message(FreeTestFlow.goal)
    async def free_goal_text(m: Message, state: FSMContext):
        txt = safe_text(m)
        if not txt:
            return await m.answer("Напиши цель теста *текстом* одним сообщением.")
        db.update_test_field(m.from_user.id, "goal", txt)
        await state.set_state(FreeTestFlow.material)
        await m.answer(
            "Отправь исходник:\n"
            "1) *видео файлом* (лучше)\n"
            "или\n"
            "2) *ссылку текстом* одним сообщением."
        )

    # Материал: только VIDEO или TEXT
    @dp.message(FreeTestFlow.material)
    async def free_material(m: Message, state: FSMContext):
        if m.video:
            db.update_test_field(m.from_user.id, "material_type", "video")
            db.update_test_field(m.from_user.id, "material_value", m.video.file_id)
            material_label = "video(file_id)"
        elif m.text and m.text.strip():
            link = m.text.strip()
            db.update_test_field(m.from_user.id, "material_type", "link")
            db.update_test_field(m.from_user.id, "material_value", link)
            material_label = "link"
        else:
            return await m.answer(
                "❌ Сейчас пришло не видео и не ссылка.\n\n"
                "Пришли:\n"
                "1️⃣ 🎥 видео *файлом* (📎 → Видео)\n"
                "или\n"
                "2️⃣ 🔗 ссылку *текстом* одним сообщением."
            )

        db.set_test_day(m.from_user.id, 1)

        # мониторинг: исходник получен
        last = db.get_last_test_fields(m.from_user.id)
        await notify_admin(
            "📥 Free тест: исходник получен\n"
            f"User: {safe_username(m.from_user.username)} | id={m.from_user.id}\n"
            f"Niche: {last.get('niche','—')}\n"
            f"TikTok: {last.get('tiktok_link','—')}\n"
            f"Goal: {last.get('goal','—')}\n"
            f"Material: {material_label}"
        )

        await state.clear()
        await m.answer(
            "✅ Принято. *День 1* стартовал.\n"
            "Видео №1 — тестируем хук и удержание.\n"
            "Выложи в течение 24 часов.",
            reply_markup=kb.day_actions_kb()
        )

    @dp.callback_query(F.data == "free:rules")
    async def free_rules(c: CallbackQuery):
        await c.message.answer(texts.FREE_RULES_MINI)
        await c.answer()

    @dp.callback_query(F.data == "free:posted")
    async def free_posted(c: CallbackQuery, state: FSMContext):
        day = db.get_test_day(c.from_user.id)
        await state.set_state(FreeTestFlow.day_publish_link)
        await c.message.answer(f"Ок. Пришли ссылку на опубликованное видео (День {day}) *текстом*.")
        await c.answer()

    @dp.message(FreeTestFlow.day_publish_link)
    async def free_post_link(m: Message, state: FSMContext):
        link = safe_text(m)
        if not link:
            return await m.answer("Пришли ссылку *текстом* (не файлом/стикером).")

        # сохраняем для следующего шага статистики
        await state.update_data(post_link=link)

        # мониторинг: ссылка на пост
        day = db.get_test_day(m.from_user.id)
        await notify_admin(
            "🔗 Free тест: ссылка на пост\n"
            f"User: {safe_username(m.from_user.username)} | id={m.from_user.id}\n"
            f"Day: {day}\n"
            f"Post: {link}"
        )

        # сбрасываем только state (данные остаются)
        await state.set_state(None)

        await m.answer("Ссылка сохранена. Теперь введём статистику.", reply_markup=kb.after_posted_kb())

    @dp.callback_query(F.data == "free:stats")
    async def free_stats_start(c: CallbackQuery, state: FSMContext):
        await state.set_state(FreeTestFlow.stats_views)
        await c.message.answer("Просмотры (числом):")
        await c.answer()

    @dp.message(FreeTestFlow.stats_views)
    async def free_stats_views(m: Message, state: FSMContext):
        txt = safe_text(m)
        if not txt or not is_int(txt):
            return await m.answer("Введи число просмотров.")
        await state.update_data(views=int(txt))
        await state.set_state(FreeTestFlow.stats_likes)
        await m.answer("Лайки (числом):")

    @dp.message(FreeTestFlow.stats_likes)
    async def free_stats_likes(m: Message, state: FSMContext):
        txt = safe_text(m)
        if not txt or not is_int(txt):
            return await m.answer("Введи число лайков.")
        await state.update_data(likes=int(txt))
        await state.set_state(FreeTestFlow.stats_comments)
        await m.answer("Комментарии (числом):")

    @dp.message(FreeTestFlow.stats_comments)
    async def free_stats_comments(m: Message, state: FSMContext):
        txt = safe_text(m)
        if not txt or not is_int(txt):
            return await m.answer("Введи число комментариев.")
        await state.update_data(comments=int(txt))
        await state.set_state(FreeTestFlow.stats_follows)
        await m.answer("Подписки/переходы (если нет — 0):")

    @dp.message(FreeTestFlow.stats_follows)
    async def free_stats_follows(m: Message, state: FSMContext):
        txt = safe_text(m)
        if not txt or not is_int(txt):
            return await m.answer("Введи число (можно 0).")

        data = await state.get_data()
        day = db.get_test_day(m.from_user.id)

        post_link = data.get("post_link", "—")
        views = data.get("views", 0)
        likes = data.get("likes", 0)
        comments = data.get("comments", 0)
        follows = int(txt)

        db.add_stats(m.from_user.id, day, post_link, views, likes, comments, follows)

        # мониторинг: статистика
        await notify_admin(
            "📊 Free тест: статистика\n"
            f"User: {safe_username(m.from_user.username)} | id={m.from_user.id}\n"
            f"Day: {day}\n"
            f"Views: {views}, Likes: {likes}, Comments: {comments}, Follows: {follows}\n"
            f"Post: {post_link}"
        )

        if day < 3:
            db.set_test_day(m.from_user.id, day + 1)
            await state.clear()
            await m.answer(
                f"✅ Сохранили статистику (День {day}).\n\n"
                f"*День {day+1}* стартовал.\n"
                "Новое видео — следующая вариация формата/хука.\n"
                "Выложи в течение 24 часов.",
                reply_markup=kb.day_actions_kb()
            )
        else:
            db.finish_test(m.from_user.id)
            await state.clear()

            rows = db.get_stats_for_last_test(m.from_user.id)
            report = make_test_report(rows)

            last = db.get_last_test_fields(m.from_user.id)
            await notify_admin(
                "🟩 Free тест завершён\n"
                f"User: {safe_username(m.from_user.username)} | id={m.from_user.id}\n"
                f"Niche: {last.get('niche','—')}\n"
                f"TikTok: {last.get('tiktok_link','—')}\n"
                f"Goal: {last.get('goal','—')}\n"
                "Action: можно дожимать на Premium / Lux."
            )

            await m.answer(report)
            await m.answer(texts.AFTER_TEST_SUMMARY, reply_markup=kb.after_test_kb(cfg.manager_username))

    # FSM fallback: отвечает ТОЛЬКО если пользователь сейчас в каком-то стейте
    @dp.message(StateFilter("*"))
    async def fsm_fallback(m: Message, state: FSMContext):
        if await state.get_state() is None:
            return
        await m.answer(
            "Я жду ответ *текстом* или *видео файлом* по текущему шагу.\n"
            "Если нужно — нажми /start."
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
