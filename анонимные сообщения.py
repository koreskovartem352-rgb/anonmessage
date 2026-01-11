import asyncio
import logging
import base64
import html
import urllib.parse
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery, ReplyParameters, LinkPreviewOptions,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8529541741:AAHhIEZxfyAxqksM41GioN7_8eo7m6kXUFY"
SUPER_ADMIN_ID = 8373944464  
moderators = {8373944464, 5061305324, 1287903671, 6156312780} 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Хранилища
reply_storage = {}  
blocked_users = {}  
user_stats = {} # {user_id: {'t_msg': 0, 'all_msg': 0, 't_view': 0, 'all_view': 0, 'date': 'iso'}}

class AnonState(StatesGroup):
    waiting_for_message = State()
    recipient_id = State()
    prompt_msg_id = State() 
    waiting_for_mod_id = State()

# --- ШАБЛОНЫ ТЕКСТОВ ---

INSTRUCTION = (
    "🚀 Здесь можно отправить анонимное сообщение человеку, который опубликовал эту ссылку.\n\n"
    "✍️ Напишите сюда всё, что хотите ему передать, и через несколько секунд "
    "он получит ваше сообщение, но не будет знать от кого.\n\n"
    "Отправить можно фото, видео, 💬 текст, 🔊 голосовые, 📷 видеосообщения (кружки), а также ✨ стикеры"
)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отменить ❌", callback_data="cancel_send")]])

def check_stats_reset(user_id):
    """Сбрасывает дневную статистику, если наступил новый день"""
    today = datetime.now().date().isoformat()
    if user_id not in user_stats:
        user_stats[user_id] = {'t_msg': 0, 'all_msg': 0, 't_view': 0, 'all_view': 0, 'date': today}
    if user_stats[user_id]['date'] != today:
        user_stats[user_id]['t_msg'] = 0
        user_stats[user_id]['t_view'] = 0
        user_stats[user_id]['date'] = today

def encode_payload(user_id: int) -> str:
    return base64.urlsafe_b64encode(str(user_id).encode()).decode().rstrip("=")

def decode_payload(payload: str) -> int:
    try:
        padding = '=' * (4 - (len(payload) % 4))
        return int(base64.urlsafe_b64decode(payload + padding).decode())
    except: return None

async def get_start_info(user_id: int):
    bot_info = await bot.get_me()
    link = f"t.me/{bot_info.username}?start={encode_payload(user_id)}"
    text = (
        "Начни получать анонимные сообщения прямо сейчас 🚀\n\n"
        "Твоя ссылка 👇\n"
        f"<blockquote>{link}</blockquote>\n\n"
        "Размести эту ссылку ☝️ в описании профиля Telegram/TikTok/Instagram, "
        "чтобы начать получать анонимные сообщения 💬"
    )
    share_text = f"По этой ссылке можно прислать мне **анонимное сообщение**:\n\n👉 {link}"
    share_url = f"https://t.me/share/url?text={urllib.parse.quote(share_text)}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Поделиться ссылкой 🔗", url=share_url)]])
    return text, kb

def get_msg_inline_kb(sender_id: int, recipient_id: int, is_blocked: bool = False, is_revealed: bool = False):
    btns = []
    b_text = "Разблокировать ✅" if is_blocked else "Заблокировать 🚫"
    btns.append([InlineKeyboardButton(text=b_text, callback_data=f"{'un' if is_blocked else ''}block_{sender_id}")])
    if recipient_id in moderators:
        r_text = "Скрыть автора 🙈" if is_revealed else "Раскрыть автора 👁"
        btns.append([InlineKeyboardButton(text=r_text, callback_data=f"{'hide' if is_revealed else 'reveal'}_{sender_id}")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

# --- СТАТИСТИКА (ИСПРАВЛЕНА) ---

@router.message(Command("stats"))
@router.message(F.text == "Статистика")
async def show_stats(message: Message):
    uid = message.from_user.id
    check_stats_reset(uid)
    s = user_stats[uid]
    bot_info = await bot.get_me()
    link = f"t.me/{bot_info.username}?start={encode_payload(uid)}"
    
    text = (
        "📌 Статистика профиля\n\n"
        "➖ Сегодня:\n"
        f"💬 Сообщений: {s['t_msg']}\n"
        f"👀 Переходов по ссылке: {s['t_view']}\n"
        "⭐️ Популярность: 1000+ место\n\n"
        "➖ За всё время:\n"
        f"💬 Сообщений: {s['all_msg']}\n"
        f"👀 Переходов по ссылке: {s['all_view']}\n"
        "⭐️ Популярность: 1000+ место\n\n"
        "Чтобы поднять ⭐️ уровень популярности, распространяйте свою персональную ссылку:\n"
        f"👉 {link}"
    )
    _, kb = await get_start_info(uid)
    await message.answer(text, reply_markup=kb, link_preview_options=LinkPreviewOptions(is_disabled=True))

# --- ОСНОВНЫЕ ХЕНДЛЕРЫ ---

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    payload = command.args
    user_id = message.from_user.id
    check_stats_reset(user_id)
    
    if not payload:
        text, kb = await get_start_info(user_id)
        await message.answer(text, reply_markup=kb, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))
        if user_id == SUPER_ADMIN_ID:
            adm_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="➕ Добавить модератора"), KeyboardButton(text="➖ Убрать модератора")], [KeyboardButton(text="📋 Список модераторов")]], resize_keyboard=True)
            await message.answer("Админ-панель активирована", reply_markup=adm_kb)
        return

    recipient_id = decode_payload(payload)
    if recipient_id:
        # СЧИТАЕМ ПЕРЕХОД
        check_stats_reset(recipient_id)
        user_stats[recipient_id]['t_view'] += 1
        user_stats[recipient_id]['all_view'] += 1
        
        await state.update_data(recipient_id=recipient_id)
        await state.set_state(AnonState.waiting_for_message)
        p = await message.answer(INSTRUCTION, reply_markup=get_cancel_kb())
        await state.update_data(prompt_msg_id=p.message_id)

@router.message(AnonState.waiting_for_message)
async def process_anon_message(message: Message, state: FSMContext):
    data = await state.get_data()
    rid = data.get("recipient_id")
    pid = data.get("prompt_msg_id")
    sid = message.from_user.id
    
    is_blocked = (rid in blocked_users and sid in blocked_users[rid])
    h = "✨ У тебя новое анонимное сообщение!"
    f = "↩️ Свайпни для ответа."
    kb = get_msg_inline_kb(sid, rid)

    if not is_blocked:
        try:
            # СЧИТАЕМ ПРИШЕДШЕЕ СООБЩЕНИЕ
            check_stats_reset(rid)
            user_stats[rid]['t_msg'] += 1
            user_stats[rid]['all_msg'] += 1
            
            sent = None
            if message.text:
                sent = await bot.send_message(rid, f"{h}\n\n{html.escape(message.text)}\n\n{f}", reply_markup=kb, parse_mode="HTML")
            elif message.sticker or message.video_note:
                await bot.send_message(rid, h)
                sent = await message.copy_to(rid, reply_markup=kb)
                await bot.send_message(rid, f)
            else:
                cap = f"{h}\n{html.escape(message.caption or '')}\n{f}".strip()
                sent = await message.copy_to(rid, caption=cap, reply_markup=kb, parse_mode="HTML")
            if sent:
                reply_storage[sent.message_id] = (sid, message.message_id)
        except: pass

    await state.clear()
    if pid:
        try: await bot.delete_message(message.chat.id, pid)
        except: pass
    
    more_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отправить еще 💬", callback_data=f"write_more_{rid}")]])
    await message.reply("🏖️ Сообщение отправлено, ожидайте ответ!", reply_markup=more_kb)
    
    txt, mkb = await get_start_info(sid)
    await message.answer(txt, reply_markup=mkb, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))

@router.callback_query(F.data.startswith(("reveal_", "hide_")))
async def toggle_reveal(callback: CallbackQuery):
    action, sender_id_str = callback.data.split("_")
    sender_id = int(sender_id_str)
    is_revealed = (action == "reveal")
    user_info = await bot.get_chat(sender_id)
    if user_info.username: auth = f"@{user_info.username}"
    else: auth = f'<a href="tg://user?id={sender_id}">{html.escape(user_info.first_name)}</a>'
    
    cur_text = callback.message.text or callback.message.caption or ""
    header = "✨ У тебя новое анонимное сообщение!"
    footer = "↩️ Свайпни для ответа."
    
    clean = cur_text.replace(header, "").replace(footer, "").strip()
    if "👤 Автор:" in clean:
        clean = clean.split("👤 Автор:")[0].strip()

    final_text = f"{header}\n\n{clean}\n\n👤 Автор: {auth}\n\n{footer}" if is_revealed else f"{header}\n\n{clean}\n\n{footer}"
    new_kb = get_msg_inline_kb(sender_id, callback.from_user.id, is_revealed=is_revealed)

    if callback.message.text:
        await callback.message.edit_text(final_text, reply_markup=new_kb, parse_mode="HTML")
    else:
        await callback.message.edit_caption(caption=final_text, reply_markup=new_kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("write_more_"))
async def write_more(callback: CallbackQuery, state: FSMContext):
    rid = int(callback.data.split("_")[2])
    await state.update_data(recipient_id=rid)
    await state.set_state(AnonState.waiting_for_message)
    p = await callback.message.answer(INSTRUCTION, reply_markup=get_cancel_kb())
    await state.update_data(prompt_msg_id=p.message_id)
    await callback.answer()

@router.message(F.reply_to_message)
async def handle_reply(message: Message):
    rid = message.reply_to_message.message_id
    if rid not in reply_storage: return
    osid, omid = reply_storage[rid]
    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Написать еще ✍️", callback_data=f"write_more_{message.from_user.id}")]])
        await message.copy_to(chat_id=osid, reply_parameters=ReplyParameters(message_id=omid), reply_markup=kb)
        await message.answer("🕊 Ваш ответ отправлен успешно")
    except: await message.answer("❌ Ошибка доставки.")

@router.callback_query(F.data == "cancel_send")
async def cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await callback.message.delete()
    except: pass
    t, k = await get_start_info(callback.from_user.id)
    await callback.message.answer(t, reply_markup=k, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))

@router.callback_query(F.data.contains("block"))
async def block_toggle(callback: CallbackQuery):
    act, sid = callback.data.split("_")
    sid = int(sid)
    rid = callback.from_user.id
    if "unblock" in act:
        if rid in blocked_users: blocked_users[rid].discard(sid)
    else:
        if rid not in blocked_users: blocked_users[rid] = set()
        blocked_users[rid].add(sid)
    await callback.message.edit_reply_markup(reply_markup=get_msg_inline_kb(sid, rid, is_blocked=("unblock" not in act)))
    await callback.answer()

@router.message(F.text == "➕ Добавить модератора", F.from_user.id == SUPER_ADMIN_ID)
async def adm_add(message: Message, state: FSMContext):
    await state.set_state(AnonState.waiting_for_mod_id)
    await message.answer("Введи ID модератора:")

@router.message(F.text == "➖ Убрать модератора", F.from_user.id == SUPER_ADMIN_ID)
async def adm_rem(message: Message, state: FSMContext):
    await state.set_state(AnonState.waiting_for_mod_id)
    await message.answer("Введи ID для удаления:")

@router.message(F.text == "📋 Список модераторов", F.from_user.id == SUPER_ADMIN_ID)
async def adm_list(message: Message):
    await message.answer(f"Модераторы:\n" + "\n".join([str(i) for i in moderators]))

@router.message(AnonState.waiting_for_mod_id, F.from_user.id == SUPER_ADMIN_ID)
async def adm_proc(message: Message, state: FSMContext):
    try:
        m_id = int(message.text)
        if m_id in moderators: moderators.remove(m_id)
        else: moderators.add(m_id)
        await message.answer("Готово!")
        await state.clear()
    except: await message.answer("Нужен числовой ID.")

async def main():
    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить"),
        BotCommand(command="stats", description="Статистика"),
        BotCommand(command="idea", description="Предложить идею")
    ])
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
