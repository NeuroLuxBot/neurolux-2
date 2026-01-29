import asyncio
import logging
import re
from typing import Optional, Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, StateFilter, Command
from aiogram.fsm.context import FSMContext

from config import load_config
import texts
import keyboards as kb
import db
from states import FreeTestFlow, LuxFlow
from services import make_test_report


# -------------------- helpers --------------------

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


def norm_text(s: str) -> str:
    return re.sub(r"[\u200b-\u200f\u2060\uFEFF]", "", s or "").strip()


def parse_user_and_file(text: str) -> Tuple[Optional[int], Optional[str]]:
    t = norm_text(text)
    if not t:
        return None, None
    t = re.sub(r"^/\w+(?:@\w+)?\s*", "", t).strip()
    if not t:
        return None, None
    m = re.match(r"^(\d+)\s*(.*)$", t)
    if not m:
        return None, None
    user_id = int(m.group(1))
    rest = m.group(2).strip()
    file_id = rest if rest else None
    return user_id, file_id


async def send_err(m: Message, where: str, e: Exception):
    await m.answer(f"❌ {where}:\n{type(e).__name__}: {e}")


def truncate(s: str, n: int = 3500) -> str:
    s = s or ""
    return s if len(s) <= n else (s[: n - 3] + "...")


# -------------------- main --------------------

async def main():
    logging.basicConfig(level=logging.INFO)

    cfg = load_config()
    db.init_db()

    bot = Bot(token=cfg.bot_token, parse_mode=ParseMode.MARKDOWN)
    dp = Dispatcher()

    ADMIN_ID = int(cfg.admin_chat_id)

    last_media = {"video": None, "document": None, "photo": None}

    # ✅ НОВЫЙ ТЕКСТ ДЛЯ КНОПКИ "Как правильно выложить видео?"
    FREE_RULES_NEW_TEXT = (
        "⏰ Время публикации:\n"
        "12:00 – 14:00\n"
        "18:00 – 22:00\n\n"
        "📊 Сколько выкладывать:\n"
        "ежедневно\n"
        "минимум 30 дней\n"
        "90% аккаунтов не растут из-за нерегулярности.\n\n"
        "🚀 Алгоритм = игровой автомат\n"
        "     Ты — игрок.\n"
        "     Видео — это ставка."
    )

    async def notify_admin(text: str):
        try:
            await bot.send_message(
                ADMIN_ID,
                text,
                parse_mode=None,
                disable_web_page_preview=True
            )
        except Exception as e:
            logging.exception(f"Admin notify error: {e}")

    async def forward_free_material_to_admin(user_id: int, username: str | None, video_id: str, desc: str):
        header = (
            "📦 Free тест — исходник + описание\n"
            f"User: {safe_username(username)} | id={user_id}\n\n"
            "📝 Описание:\n"
            f"{truncate(desc, 3500)}"
        )
        await bot.send_message(ADMIN_ID, header, parse_mode=None, disable_web_page_preview=True)
        await bot.send_video(ADMIN_ID, video_id)

    @dp.error()
    async def on_error(event, exception: Exception):
        logging.exception(f"Unhandled error: {exception}")
        return True

    # ========================= ADMIN: CAPTURE FILE_ID (ТОЛЬКО ДЛЯ АДМИНА) =========================

    @dp.message(StateFilter(None), F.from_user.id == ADMIN_ID, F.video)
    async def admin_capture_video_id(m: Message):
        v = m.video
        last_media["video"] = v.file_id
        await m.answer(
            "🎥 VIDEO FILE_ID:\n"
            f"{v.file_id}\n\n"
            "🧷 FILE_UNIQUE_ID:\n"
            f"{v.file_unique_id}\n\n"
            "✅ Сохранено как LAST VIDEO.\n"
            "`/video <user_id>` (без file_id)"
        )

    @dp.message(StateFilter(None), F.from_user.id == ADMIN_ID, F.document)
    async def admin_capture_document_id(m: Message):
        d = m.document
        last_media["document"] = d.file_id
        await m.answer(
            "📄 DOCUMENT FILE_ID:\n"
            f"{d.file_id}\n\n"
            "🧷 FILE_UNIQUE_ID:\n"
            f"{d.file_unique_id}\n\n"
            "✅ Сохранено как LAST DOC.\n"
            "`/doc <user_id>` (без file_id)"
        )

    @dp.message(StateFilter(None), F.from_user.id == ADMIN_ID, F.photo)
    async def admin_capture_photo_id(m: Message):
        p = m.photo[-1]
        last_media["photo"] = p.file_id
        await m.answer(
            "🖼 PHOTO FILE_ID:\n"
            f"{p.file_id}\n\n"
            "🧷 FILE_UNIQUE_ID:\n"
            f"{p.file_unique_id}\n\n"
            "✅ Сохранено как LAST PHOTO.\n"
            "`/photo <user_id>` (без file_id)"
        )

    @dp.message(Command("getid"))
    async def admin_getid_reply(m: Message):
        if m.from_user.id != ADMIN_ID:
            return await m.answer("⛔ Нет доступа.")

        r = m.reply_to_message
        if not r:
            return await m.answer("Формат: ответь командой /getid на сообщение с видео/фото/файлом.")

        if r.video:
            x = r.video
            last_media["video"] = x.file_id
            return await m.answer("✅ LAST VIDEO обновлён.")

        if r.document:
            x = r.document
            last_media["document"] = x.file_id
            return await m.answer("✅ LAST DOC обновлён.")

        if r.photo:
            x = r.photo[-1]
            last_media["photo"] = x.file_id
            return await m.answer("✅ LAST PHOTO обновлён.")

        return await m.answer("В reply нет видео/фото/файла.")

    # ========================= ADMIN SEND =========================

    @dp.message(Command("say"))
    async def admin_say(m: Message):
        if m.from_user.id != ADMIN_ID:
            return await m.answer("⛔ Нет доступа.")

        parts = (m.text or "").split(maxsplit=2)
        if len(parts) < 3:
            return await m.answer("Формат: /say user_id текст")

        try:
            user_id = int(parts[1])
        except ValueError:
            return await m.answer("user_id должен быть числом.")

        text = parts[2]
        try:
            await bot.send_message(user_id, text)
            await m.answer("✅ Сообщение отправлено.")
        except Exception as e:
            await send_err(m, "send_message", e)

    @dp.message(Command("photo"))
    async def admin_photo(m: Message):
        if m.from_user.id != ADMIN_ID:
            return await m.answer("⛔ Нет доступа.")

        user_id, file_id = parse_user_and_file(m.text or "")
        if user_id is None:
            return await m.answer("Формат: /photo user_id file_id | reply /photo user_id | /photo user_id (LAST PHOTO)")

        if file_id:
            try:
                await bot.send_photo(chat_id=user_id, photo=file_id)
                return await m.answer("🖼 Фото отправлено.")
            except Exception as e:
                return await send_err(m, "send_photo", e)

        if m.reply_to_message and m.reply_to_message.photo:
            fid = m.reply_to_message.photo[-1].file_id
            try:
                await bot.send_photo(chat_id=user_id, photo=fid)
                return await m.answer("🖼 Фото отправлено (reply).")
            except Exception as e:
                return await send_err(m, "send_photo(reply)", e)

        fid = last_media.get("photo")
        if not fid:
            return await m.answer("Нет LAST PHOTO.")
        try:
            await bot.send_photo(chat_id=user_id, photo=fid)
            return await m.answer("🖼 Фото отправлено (LAST).")
        except Exception as e:
            return await send_err(m, "send_photo(LAST)", e)

    @dp.message(Command("video"))
    async def admin_video(m: Message):
        if m.from_user.id != ADMIN_ID:
            return await m.answer("⛔ Нет доступа.")

        user_id, file_id = parse_user_and_file(m.text or "")
        if user_id is None:
            return await m.answer("Формат: /video user_id file_id | reply /video user_id | /video user_id (LAST VIDEO)")

        if file_id:
            try:
                await bot.send_video(chat_id=user_id, video=file_id)
                return await m.answer("🎬 Видео отправлено.")
            except Exception as e:
                return await send_err(m, "send_video", e)

        if m.reply_to_message and m.reply_to_message.video:
            fid = m.reply_to_message.video.file_id
            try:
                await bot.send_video(chat_id=user_id, video=fid)
                return await m.answer("🎬 Видео отправлено (reply).")
            except Exception as e:
                return await send_err(m, "send_video(reply)", e)

        fid = last_media.get("video")
        if not fid:
            return await m.answer("Нет LAST VIDEO.")
        try:
            await bot.send_video(chat_id=user_id, video=fid)
            return await m.answer("🎬 Видео отправлено (LAST).")
        except Exception as e:
            return await send_err(m, "send_video(LAST)", e)

    @dp.message(Command("doc"))
    async def admin_doc(m: Message):
        if m.from_user.id != ADMIN_ID:
            return await m.answer("⛔ Нет доступа.")

        user_id, file_id = parse_user_and_file(m.text or "")
        if user_id is None:
            return await m.answer("Формат: /doc user_id file_id | reply /doc user_id | /doc user_id (LAST DOC)")

        if file_id:
            try:
                await bot.send_document(chat_id=user_id, document=file_id)
                return await m.answer("📄 Файл отправлен.")
            except Exception as e:
                return await send_err(m, "send_document", e)

        if m.reply_to_message and m.reply_to_message.document:
            fid = m.reply_to_message.document.file_id
            try:
                await bot.send_document(chat_id=user_id, document=fid)
                return await m.answer("📄 Файл отправлен (reply).")
            except Exception as e:
                return await send_err(m, "send_document(reply)", e)

        fid = last_media.get("document")
        if not fid:
            return await m.answer("Нет LAST DOC.")
        try:
            await bot.send_document(chat_id=user_id, document=fid)
            return await m.answer("📄 Файл отправлен (LAST).")
        except Exception as e:
            return await send_err(m, "send_document(LAST)", e)

    # ========================= /start =========================

    @dp.message(CommandStart())
    async def start(m: Message, state: FSMContext):
        await state.clear()
        db.upsert_user(m.from_user.id, m.from_user.username)
        await m.answer(texts.START, reply_markup=kb.main_menu(cfg.manager_username))

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
            "Status: pending"
        )

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
            "Status: pending"
        )

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

    @dp.callback_query(F.data.startswith("free:goal:"))
    async def free_goal_btn(c: CallbackQuery, state: FSMContext):
        goal = c.data.split("free:goal:", 1)[1]
        db.update_test_field(c.from_user.id, "goal", goal)
        await state.set_state(FreeTestFlow.material)
        await c.message.answer(
            "Отправь исходник:\n"
            "1) *видео файлом* (лучше)\n"
            "2) *подробное описание* (текстом одним сообщением)\n\n"
            "Можно прислать в любом порядке — я подскажу, чего не хватает."
        )
        await c.answer()

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
            "2) *подробное описание* (текстом одним сообщением)\n\n"
            "Можно прислать в любом порядке — я подскажу, чего не хватает."
        )

    @dp.message(FreeTestFlow.material)
    async def free_material(m: Message, state: FSMContext):
        if m.video:
            await state.update_data(material_video_id=m.video.file_id)
        elif m.text and m.text.strip():
            await state.update_data(material_description=m.text.strip())
        else:
            return await m.answer(
                "❌ Сейчас пришло не видео и не описание.\n\n"
                "Пришли:\n"
                "1️⃣ 🎥 видео *файлом* (📎 → Видео)\n"
                "и/или\n"
                "2️⃣ 📝 подробное описание *текстом* одним сообщением."
            )

        data = await state.get_data()
        vid = data.get("material_video_id")
        desc = data.get("material_description")

        if not vid or not desc:
            missing = []
            if not vid:
                missing.append("🎥 видео файлом")
            if not desc:
                missing.append("📝 подробное описание текстом")
            return await m.answer("Осталось прислать: " + " + ".join(missing))

        # ВАЖНО: в твоём db.py сейчас нет полей material_video_id/material_description.
        # Поэтому сохраняем в существующие поля:
        db.update_test_field(m.from_user.id, "material_type", "video+description")
        db.update_test_field(m.from_user.id, "material_value", vid)  # file_id видео

        db.set_test_day(m.from_user.id, 1)

        # Пересылаем тебе в личку видео + описание
        try:
            await forward_free_material_to_admin(m.from_user.id, m.from_user.username, vid, desc)
        except Exception as e:
            logging.exception(f"Forward to admin failed: {e}")

        last = db.get_last_test_fields(m.from_user.id)
        await notify_admin(
            "📥 Free тест: исходник + описание приняты\n"
            f"User: {safe_username(m.from_user.username)} | id={m.from_user.id}\n"
            f"Niche: {last.get('niche','—')}\n"
            f"TikTok: {last.get('tiktok_link','—')}\n"
            f"Goal: {last.get('goal','—')}\n"
            "Material: video(file_id) + description"
        )

        await state.clear()
        await m.answer(
            "✅ Принято. *День 1* стартовал.\n"
            "Видео №1 — тестируем хук и удержание.\n"
            "Выложи в течение 24 часов.",
            reply_markup=kb.day_actions_kb()
        )

    # ✅ ИСПРАВЛЕНО: кнопка "Как правильно выложить видео?" теперь отдаёт твой новый текст
    @dp.callback_query(F.data == "free:rules")
    async def free_rules(c: CallbackQuery):
        await c.message.answer(FREE_RULES_NEW_TEXT, parse_mode=None)
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

        await state.update_data(post_link=link)

        day = db.get_test_day(m.from_user.id)
        await notify_admin(
            "🔗 Free тест: ссылка на пост\n"
            f"User: {safe_username(m.from_user.username)} | id={m.from_user.id}\n"
            f"Day: {day}\n"
            f"Post: {link}"
        )

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

        await notify_admin(
            "📊 Free тест: статистика\n"
            f"User: {safe_username(m.from_user.username)} | id={m.from_user.id}\n"
            f"Day: {day}\n"
            f"Views: {views}, Likes: {likes}, Comments: {comments}\n"
            f"Follows: {follows}\n"
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

    @dp.message(StateFilter("*"))
    async def fsm_fallback(m: Message, state: FSMContext):
        if await state.get_state() is None:
            return
        await m.answer("Я жду ответ по текущему шагу. Если нужно — нажми /start.")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
