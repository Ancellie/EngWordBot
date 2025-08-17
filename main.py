import re
import random
import atexit

import page
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from db_manager import DatabaseManager

TOKEN = ""

# Ініціалізуємо менеджер бази даних
db = DatabaseManager()

# Зберігання даних для користувачів (тимчасове, під час роботи)
user_data = {}


def init_user_data(user_id):
    """Ініціалізація даних користувача"""
    if user_id not in user_data:
        # Спробуємо отримати дані з БД
        saved_data = db.get_user_data(user_id)

        if saved_data:
            # Якщо є дані в БД, використовуємо їх
            user_data[user_id] = saved_data
        else:
            # Якщо даних немає, створюємо нові
            user_data[user_id] = {
                'words': [],  # [(eng, ukr), ...]
                'current_index': 0
            }
            # Зберігаємо початкові дані в БД
            db.save_user_data(user_id, user_data[user_id])


def escape_markdown_v2(text):
    """Екранування спеціальних символів для MarkdownV2"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def parse_word_list(text):
    """Парсинг списку слів з різними роздільниками"""
    lines = text.strip().split('\n')
    words = []

    # Можливі роздільники
    separators = [' - ', ' – ', ' — ', ' | ', ' : ', ' ; ', '\t']

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Пробуємо різні роздільники
        for sep in separators:
            if sep in line:
                parts = line.split(sep, 1)
                if len(parts) == 2:
                    eng = parts[0].strip()
                    ukr = parts[1].strip()
                    if eng and ukr:
                        words.append((eng, ukr))
                    break
        else:
            # Якщо не знайдено роздільник, спробуємо пробіл
            parts = line.split()
            if len(parts) >= 2:
                # Перша частина - англійське слово, решта - переклад
                eng = parts[0]
                ukr = ' '.join(parts[1:])
                words.append((eng, ukr))

    return words


def get_main_keyboard():
    """Створення основної клавіатури"""
    keyboard = [
        [InlineKeyboardButton("➕ Додати слова", callback_data="add_words")],
        [InlineKeyboardButton("📚 Наступне слово", callback_data="next_word")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🗑️ Керування словами", callback_data="manage_words")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_manage_keyboard():
    """Клавіатура для керування словами"""
    keyboard = [
        [InlineKeyboardButton("🗑️ Видалити всі слова", callback_data="delete_all")],
        [InlineKeyboardButton("❌ Видалити конкретне слово", callback_data="delete_specific")],
        [InlineKeyboardButton("📝 Показати всі слова", callback_data="show_all")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user_id = update.effective_user.id
    init_user_data(user_id)

    welcome_text = """🎓 Привіт! Це бот для вивчення слів.

📝 Щоб почати, додай слова у форматі:
word - переклад
apple - яблуко
book - книга

🎯 Можливості бота:
• Додавання нових слів
• Перегляд слів для вивчення
• Керування списком слів
• Статистика навчання

Натисни кнопку щоб почати! 👇"""

    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник натискань кнопок"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    init_user_data(user_id)

    data = query.data

    if data == "add_words":
        await query.edit_message_text(
            "📝 Надішли мені список слів у одному з форматів:\n\n"
            "word - переклад\n"
            "word | переклад\n"
            "word : переклад\n"
            "word переклад\n\n"
            "Кожне слово з нового рядка."
        )
        context.user_data['waiting_for_words'] = True

    elif data == "next_word":
        await show_next_word(query, user_id)

    elif data == "stats":
        await show_stats(query, user_id)

    elif data == "manage_words":
        await query.edit_message_text(
            "🗑️ Керування словами:",
            reply_markup=get_manage_keyboard()
        )

    elif data == "delete_all":
        await confirm_delete_all(query, user_id)

    elif data == "confirm_delete_all":
        user_data[user_id]['words'] = []
        user_data[user_id]['current_index'] = 0

        # Зберігаємо оновлені дані в БД
        db.save_user_data(user_id, user_data[user_id])

        await query.edit_message_text(
            "✅ Всі слова видалено!",
            reply_markup=get_main_keyboard()
        )

    elif data == "delete_specific":
        await show_words_for_deletion(query, user_id, 0)

    elif data.startswith("delete_page_"):
        page = int(data.replace("delete_page_", ""))
        await show_words_for_deletion(query, user_id, page)

    elif data == "show_all":
        await show_all_words(query, user_id, 0)

    elif data.startswith("words_page_"):
        page = int(data.replace("words_page_", ""))
        await show_all_words(query, user_id, page)

    elif data.startswith("delete_word_"):
        word_index = int(data.replace("delete_word_", ""))
        await delete_specific_word(query, user_id, word_index)

    elif data == "back_to_main":
        await query.edit_message_text(
            "🏠 Головне меню:",
            reply_markup=get_main_keyboard()
        )




async def show_next_word(query, user_id):
    """Показати наступне слово"""
    words = user_data[user_id]['words']

    if not words:
        await query.edit_message_text(
            "📭 У тебе ще немає слів! Додай їх спочатку.",
            reply_markup=get_main_keyboard()
        )
        return

    # Отримуємо індекс поточного слова
    current_idx = user_data[user_id]['current_index']

    word, translation = words[current_idx]

    # Переходимо до наступного слова
    user_data[user_id]['current_index'] = (user_data[user_id]['current_index'] + 1) % len(words)

    # Зберігаємо оновлені дані користувача в БД
    db.save_user_data(user_id, user_data[user_id])

    # Додаємо кнопки для управління
    keyboard = [
        [InlineKeyboardButton("➡️ Наступне слово", callback_data="next_word")],
        [InlineKeyboardButton("🏠 Головне меню", callback_data="back_to_main")]
    ]

    # Формуємо повідомлення та відправляємо
    text = f"🔤 {word} - {translation}"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_stats(query, user_id):
    """Показати статистику"""
    words = user_data[user_id]['words']
    total_words = len(words)

    stats_text = f"""📊 **Статистика:**

📚 Всього слів: {total_words}

{f"▶️ Поточне слово: {user_data[user_id]['current_index'] + 1}/{total_words}" if total_words > 0 else ""}"""

    await query.edit_message_text(stats_text, reply_markup=get_main_keyboard())


async def confirm_delete_all(query, user_id):
    """Підтвердження видалення всіх слів"""
    keyboard = [
        [InlineKeyboardButton("✅ Так, видалити всі", callback_data="confirm_delete_all")],
        [InlineKeyboardButton("❌ Ні, залишити", callback_data="manage_words")]
    ]

    await query.edit_message_text(
        f"⚠️ Ти впевнений що хочеш видалити всі {len(user_data[user_id]['words'])} слів?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )




async def delete_specific_word(query, user_id, word_index):
    """Видалити конкретне слово"""
    words = user_data[user_id]['words']

    if 0 <= word_index < len(words):
        deleted_word = words.pop(word_index)

        # Оновлюємо індекси після видалення
        if user_data[user_id]['current_index'] >= len(words) and words:
            user_data[user_id]['current_index'] = 0

        # Зберігаємо оновлені дані в БД
        db.save_user_data(user_id, user_data[user_id])

        await query.edit_message_text(
            f"✅ Слово '{deleted_word[0]} - {deleted_word[1]}' видалено!",
            reply_markup=get_manage_keyboard()
        )
    else:
        await query.edit_message_text(
            "❌ Помилка при видаленні слова!",
            reply_markup=get_manage_keyboard()
        )


    async def show_all_words(query, user_id, page=0):
        """Показати всі слова з пагінацією"""
    words = user_data[user_id]['words']

    if not words:
        await query.edit_message_text(
            "📭 У тебе ще немає слів!",
            reply_markup=get_manage_keyboard()
        )
        return

    # Кількість слів на сторінці
    page_size = 20
    total_pages = (len(words) + page_size - 1) // page_size

    # Визначаємо діапазон слів для поточної сторінки
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(words))

    # Формуємо текст зі словами
    text = f"📚 **Твої слова ({len(words)}):**\n"
    text += f"Сторінка {page+1}/{total_pages} (слова {start_idx+1}-{end_idx})\n\n"

    for i in range(start_idx, end_idx):
        word, translation = words[i]
        text += f"{i+1}. {word} - {translation}\n"

    # Створюємо кнопки навігації
    keyboard = []
    nav_buttons = []

    # Кнопка «Назад» на попередню сторінку
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"words_page_{page-1}"))

    # Кнопка «Вперед» на наступну сторінку
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"words_page_{page+1}"))

    # Додаємо навігаційні кнопки, якщо їх більше нуля
    if nav_buttons:
        keyboard.append(nav_buttons)

    # Кнопка повернення до меню управління
    keyboard.append([InlineKeyboardButton("↩️ До меню керування", callback_data="manage_words")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


    async def show_all_words(query, user_id, page=0):
        """Показати всі слова з пагінацією"""
    words = user_data[user_id]['words']

    if not words:
        await query.edit_message_text(
            "📭 У тебе ще немає слів!",
            reply_markup=get_manage_keyboard()
        )
        return

    # Кількість слів на сторінці
    page_size = 20
    total_pages = (len(words) + page_size - 1) // page_size

    # Визначаємо діапазон слів для поточної сторінки
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(words))

    # Формуємо текст зі словами
    text = f"📚 **Твої слова ({len(words)}):**\n"
    text += f"Сторінка {page+1}/{total_pages} (слова {start_idx+1}-{end_idx})\n\n"

    for i in range(start_idx, end_idx):
        word, translation = words[i]
        text += f"{i+1}. {word} - {translation}\n"

    # Створюємо кнопки навігації
    keyboard = []
    nav_buttons = []

    # Кнопка «Назад» на попередню сторінку
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"words_page_{page-1}"))

    # Кнопка «Вперед» на наступну сторінку
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"words_page_{page+1}"))

    # Додаємо навігаційні кнопки, якщо їх більше нуля
    if nav_buttons:
        keyboard.append(nav_buttons)

    # Кнопка повернення до меню управління
    keyboard.append([InlineKeyboardButton("↩️ До меню керування", callback_data="manage_words")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_words_for_deletion(query, user_id, page=0):
    """Показати слова для видалення з пагінацією"""
    words = user_data[user_id]['words']

    if not words:
        await query.edit_message_text(
            "📭 У тебе немає слів для видалення!",
            reply_markup=get_manage_keyboard()
        )
        return

    # Кількість слів на сторінці
    page_size = 10
    total_pages = (len(words) + page_size - 1) // page_size

    # Визначаємо діапазон слів для поточної сторінки
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(words))

    # Створюємо кнопки для слів на поточній сторінці
    keyboard = []
    for i in range(start_idx, end_idx):
        word, translation = words[i]
        # Обмежуємо довжину тексту кнопки для кращого відображення
        button_text = f"❌ {word} - {translation}"
        if len(button_text) > 30:
            button_text = f"❌ {word} - {translation[:20]}..."

        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"delete_word_{i}"
        )])

    # Додаємо навігаційні кнопки
    nav_buttons = []

    # Кнопка «Назад» на попередню сторінку
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"delete_page_{page-1}"))

    # Кнопка «Вперед» на наступну сторінку
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"delete_page_{page+1}"))

    # Додаємо навігаційні кнопки, якщо їх більше нуля
    if nav_buttons:
        keyboard.append(nav_buttons)

    # Кнопка повернення до меню управління
    keyboard.append([InlineKeyboardButton("↩️ До меню керування", callback_data="manage_words")])

    # Формуємо текст повідомлення
    text = f"🗑️ Вибери слово для видалення (сторінка {page+1}/{total_pages}):\n"
    text += f"Показано слова {start_idx+1}-{end_idx} з {len(words)}"

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_all_words(query, user_id, page=0):
    """Показати всі слова з пагінацією"""
    words = user_data[user_id]['words']

    if not words:
        await query.edit_message_text(
            "📭 У тебе ще немає слів!",
            reply_markup=get_manage_keyboard()
        )
        return

    # Кількість слів на сторінці
    page_size = 20
    total_pages = (len(words) + page_size - 1) // page_size

    # Визначаємо діапазон слів для поточної сторінки
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(words))

    # Формуємо текст зі словами
    text = f"📚 **Твої слова ({len(words)}):**\n"
    text += f"Сторінка {page+1}/{total_pages} (слова {start_idx+1}-{end_idx})\n\n"

    for i in range(start_idx, end_idx):
        word, translation = words[i]
        text += f"{i+1}. {word} - {translation}\n"

    # Створюємо кнопки навігації
    keyboard = []
    nav_buttons = []

    # Кнопка «Назад» на попередню сторінку
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"words_page_{page-1}"))

    # Кнопка «Вперед» на наступну сторінку
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"words_page_{page+1}"))

    # Додаємо навігаційні кнопки, якщо їх більше нуля
    if nav_buttons:
        keyboard.append(nav_buttons)

    # Кнопка повернення до меню управління
    keyboard.append([InlineKeyboardButton("↩️ До меню керування", callback_data="manage_words")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def receive_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отримання списку слів"""
    if not context.user_data.get('waiting_for_words'):
        return

    user_id = update.effective_user.id
    init_user_data(user_id)

    text = update.message.text
    new_words = parse_word_list(text)

    if new_words:
        # Додаємо нові слова до існуючих
        user_data[user_id]['words'].extend(new_words)

        # Зберігаємо оновлені дані в БД
        db.save_user_data(user_id, user_data[user_id])

        await update.message.reply_text(
            f"✅ Додано {len(new_words)} нових слів!\n"
            f"📚 Всього слів: {len(user_data[user_id]['words'])}",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Не вдалося розпізнати слова. Перевір формат:\n\n"
            "word - переклад\n"
            "apple - яблуко\n"
            "book - книга"
        )

    context.user_data['waiting_for_words'] = False


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробка помилок"""
    print(f"Exception while handling an update: {context.error}")


def main():
    """Запуск бота"""
    app = Application.builder().token(TOKEN).build()

    # Обробники
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_words))

    # Додаємо обробник помилок
    app.add_error_handler(error_handler)

    # Зареєструємо функцію для закриття з'єднання з БД при завершенні роботи
    atexit.register(db.close)

    print("🤖 Бот запущено!")
    app.run_polling()


if __name__ == "__main__":
    main()
