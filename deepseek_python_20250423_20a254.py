import json
import logging
import os
from datetime import datetime
from typing import Dict, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Настройка логгирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы для состояний
REGISTER, CREATE_TICKET = range(2)
ADMIN_ACTIONS = 1

# Инициализация базы данных
def init_db():
    os.makedirs('data', exist_ok=True)
    db_files = {
        'users': 'data/users.json',
        'tickets': 'data/tickets.json',
        'admins': 'data/admins.json'
    }
    
    for file in db_files.values():
        if not os.path.exists(file):
            with open(file, 'w') as f:
                json.dump([], f)
    
    # Создаем администратора по умолчанию
    admins_file = db_files['admins']
    with open(admins_file, 'r+') as f:
        admins = json.load(f)
        if not admins:
            admins.append({
                'user_id': 'ADMIN_CHAT_ID',  # Замените на ваш chat_id
                'username': 'admin',
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            f.seek(0)
            json.dump(admins, f, indent=4)

def load_db(file_name):
    with open(f'data/{file_name}.json', 'r') as f:
        return json.load(f)

def save_db(data, file_name):
    with open(f'data/{file_name}.json', 'w') as f:
        json.dump(data, f, indent=4)

# Инициализация при запуске
init_db()

# Клавиатуры
def main_menu(user_is_admin=False):
    buttons = [
        ["📝 Создать заявку"],
        ["📋 Мои заявки"]
    ]
    if user_is_admin:
        buttons.append(["👑 Админ-панель"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def admin_menu():
    buttons = [
        ["📊 Все заявки"],
        ["🔄 Активные заявки"],
        ["✅ Закрытые заявки"],
        ["🔙 Главное меню"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def ticket_actions(ticket_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 В работу", callback_data=f"process_{ticket_id}"),
            InlineKeyboardButton("✅ Закрыть", callback_data=f"close_{ticket_id}")
        ],
        [
            InlineKeyboardButton("💬 Ответить", callback_data=f"reply_{ticket_id}")
        ]
    ])

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    users = load_db('users')
    
    # Проверяем администратора
    admins = load_db('admins')
    is_admin = any(admin['user_id'] == user_id for admin in admins)
    
    # Проверяем регистрацию пользователя
    user_exists = any(u['user_id'] == user_id for u in users)
    
    if user_exists:
        await update.message.reply_text(
            f"👋 Добро пожаловать, {user.full_name}!\n"
            "Выберите действие:",
            reply_markup=main_menu(is_admin)
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "📝 Для начала работы пройдите регистрацию.\n"
            "Введите ваше ФИО:",
            reply_markup=ReplyKeyboardRemove()
        )
        return REGISTER

async def register_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['fio'] = update.message.text
    await update.message.reply_text("🏢 Введите номер кабинета:")
    return REGISTER

async def register_cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cabinet'] = update.message.text
    await update.message.reply_text("📱 Введите ваш номер телефона:")
    return REGISTER

async def register_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text
    user = update.effective_user
    users = load_db('users')
    
    new_user = {
        'user_id': str(user.id),
        'username': user.username,
        'fio': context.user_data['fio'],
        'cabinet': context.user_data['cabinet'],
        'phone': phone,
        'registered_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    users.append(new_user)
    save_db(users, 'users')
    
    # Проверяем администратора
    admins = load_db('admins')
    is_admin = any(admin['user_id'] == str(user.id) for admin in admins)
    
    await update.message.reply_text(
        "✅ Регистрация завершена!\n"
        f"👤 ФИО: {new_user['fio']}\n"
        f"🏢 Кабинет: {new_user['cabinet']}\n"
        f"📱 Телефон: {new_user['phone']}",
        reply_markup=main_menu(is_admin)
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def create_ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✍️ Опишите вашу проблему:",
        reply_markup=ReplyKeyboardRemove()
    )
    return CREATE_TICKET

async def create_ticket_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = load_db('users')
    user = next((u for u in users if u['user_id'] == user_id), None)
    
    if not user:
        await update.message.reply_text(
            "❌ Ошибка: пользователь не найден!",
            reply_markup=main_menu()
        )
        return ConversationHandler.END
    
    problem = update.message.text
    tickets = load_db('tickets')
    ticket_id = len(tickets) + 1
    
    new_ticket = {
        'id': ticket_id,
        'user_id': user_id,
        'fio': user['fio'],
        'cabinet': user['cabinet'],
        'phone': user['phone'],
        'problem': problem,
        'status': 'открыта',
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    tickets.append(new_ticket)
    save_db(tickets, 'tickets')
    
    # Уведомляем администраторов
    admins = load_db('admins')
    for admin in admins:
        try:
            await context.bot.send_message(
                chat_id=admin['user_id'],
                text=f"🚨 Новая заявка #{ticket_id}\n\n"
                     f"👤 {user['fio']}\n"
                     f"🏢 Кабинет: {user['cabinet']}\n"
                     f"📱 Телефон: {user['phone']}\n\n"
                     f"📝 Проблема:\n{problem}",
                reply_markup=ticket_actions(ticket_id)
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления администратора: {e}")
    
    await update.message.reply_text(
        f"✅ Заявка #{ticket_id} создана!\n"
        "Администратор скоро с вами свяжется.",
        reply_markup=main_menu(any(admin['user_id'] == user_id for admin in admins))
    )
    return ConversationHandler.END

async def show_user_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    tickets = load_db('tickets')
    user_tickets = [t for t in tickets if t['user_id'] == user_id]
    
    if not user_tickets:
        await update.message.reply_text(
            "📭 У вас нет созданных заявок.",
            reply_markup=main_menu()
        )
        return
    
    for ticket in user_tickets:
        status_icon = "🟢" if ticket['status'] == 'открыта' else "🟡" if ticket['status'] == 'в работе' else "🔴"
        await update.message.reply_text(
            f"{status_icon} Заявка #{ticket['id']}\n"
            f"📌 Статус: {ticket['status']}\n"
            f"📅 Дата: {ticket['created_at']}\n\n"
            f"📝 Описание:\n{ticket['problem']}",
            reply_markup=main_menu()
        )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admins = load_db('admins')
    
    if any(admin['user_id'] == user_id for admin in admins):
        await update.message.reply_text(
            "👑 Админ-панель",
            reply_markup=admin_menu()
        )
    else:
        await update.message.reply_text(
            "⛔ У вас нет прав доступа!",
            reply_markup=main_menu()
        )

async def show_all_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tickets = load_db('tickets')
    
    if not tickets:
        await update.message.reply_text(
            "📭 Нет созданных заявок.",
            reply_markup=admin_menu()
        )
        return
    
    for ticket in tickets:
        status_icon = "🟢" if ticket['status'] == 'открыта' else "🟡" if ticket['status'] == 'в работе' else "🔴"
        await update.message.reply_text(
            f"{status_icon} Заявка #{ticket['id']}\n"
            f"👤 {ticket['fio']}\n"
            f"🏢 Кабинет: {ticket['cabinet']}\n"
            f"📱 Телефон: {ticket['phone']}\n"
            f"📌 Статус: {ticket['status']}\n"
            f"📅 Дата: {ticket['created_at']}\n\n"
            f"📝 Описание:\n{ticket['problem']}",
            reply_markup=ticket_actions(ticket['id'])
        )

async def process_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    ticket_id = int(query.data.split('_')[1])
    tickets = load_db('tickets')
    
    for ticket in tickets:
        if ticket['id'] == ticket_id:
            ticket['status'] = 'в работе'
            ticket['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            break
    
    save_db(tickets, 'tickets')
    
    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            chat_id=ticket['user_id'],
            text=f"ℹ️ Ваша заявка #{ticket_id} взята в работу.\n"
                 "Скоро с вами свяжутся."
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления пользователя: {e}")
    
    await query.edit_message_text(
        f"🔄 Заявка #{ticket_id} взята в работу.",
        reply_markup=ticket_actions(ticket_id)
    )

async def close_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    ticket_id = int(query.data.split('_')[1])
    tickets = load_db('tickets')
    
    for ticket in tickets:
        if ticket['id'] == ticket_id:
            ticket['status'] = 'закрыта'
            ticket['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            break
    
    save_db(tickets, 'tickets')
    
    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            chat_id=ticket['user_id'],
            text=f"✅ Ваша заявка #{ticket_id} закрыта.\n"
                 "Спасибо за обращение!"
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления пользователя: {e}")
    
    await query.edit_message_text(
        f"✅ Заявка #{ticket_id} закрыта.",
        reply_markup=ticket_actions(ticket_id)
    )

async def reply_to_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    ticket_id = int(query.data.split('_')[1])
    context.user_data['replying_to'] = ticket_id
    await query.edit_message_text(
        f"✍️ Введите ответ для заявки #{ticket_id}:"
    )
    return ADMIN_ACTIONS

async def send_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket_id = context.user_data['replying_to']
    message = update.message.text
    tickets = load_db('tickets')
    
    ticket = next((t for t in tickets if t['id'] == ticket_id), None)
    if not ticket:
        await update.message.reply_text(
            "❌ Заявка не найдена!",
            reply_markup=admin_menu()
        )
        return ConversationHandler.END
    
    # Отправляем ответ пользователю
    try:
        await context.bot.send_message(
            chat_id=ticket['user_id'],
            text=f"📩 Ответ по заявке #{ticket_id}:\n\n{message}"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки ответа: {e}")
    
    await update.message.reply_text(
        f"✅ Ответ по заявке #{ticket_id} отправлен.",
        reply_markup=admin_menu()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Действие отменено.",
        reply_markup=main_menu()
    )
    context.user_data.clear()
    return ConversationHandler.END

def main():
    # Создаем Application и передаем токен бота
    application = Application.builder().token("7456113956:AAGD429WTSTlZz_rKRwH8eevxKRXbsq5G3Y").build()
    
    # Обработчик регистрации
    reg_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            REGISTER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, register_user),
                MessageHandler(filters.TEXT & ~filters.COMMAND, register_cabinet),
                MessageHandler(filters.TEXT & ~filters.COMMAND, register_phone)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Обработчик создания заявки
    ticket_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📝 Создать заявку$'), create_ticket_start)],
        states={
            CREATE_TICKET: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_ticket_finish)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Обработчик ответа на заявку
    reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reply_to_ticket, pattern='^reply_')],
        states={
            ADMIN_ACTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_reply)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Регистрируем обработчики
    application.add_handler(reg_conv)
    application.add_handler(ticket_conv)
    application.add_handler(reply_conv)
    
    # Команды пользователя
    application.add_handler(MessageHandler(filters.Regex('^📋 Мои заявки$'), show_user_tickets))
    
    # Команды администратора
    application.add_handler(MessageHandler(filters.Regex('^👑 Админ-панель$'), admin_panel))
    application.add_handler(MessageHandler(filters.Regex('^📊 Все заявки$'), show_all_tickets))
    application.add_handler(MessageHandler(filters.Regex('^🔙 Главное меню$'), start))
    
    # Обработчики кнопок
    application.add_handler(CallbackQueryHandler(process_ticket, pattern='^process_'))
    application.add_handler(CallbackQueryHandler(close_ticket, pattern='^close_'))
    
    # Запускаем бота
    application.run_polling()

if __name__ == "__main__":
    main()