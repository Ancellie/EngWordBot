import sqlite3
import json

class DatabaseManager:
    def __init__(self, db_name='words_bot.db'):
        self.db_name = db_name
        self.conn = None
        self.init_db()

    def init_db(self):
        """Ініціалізація бази даних"""
        self.conn = sqlite3.connect(self.db_name)
        cursor = self.conn.cursor()

        # Перевіряємо чи існує таблиця users
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = cursor.fetchone() is not None

        if table_exists:
            # Якщо таблиця існує, створюємо нову без зайвих колонок
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users_new (
                user_id INTEGER PRIMARY KEY,
                words TEXT,
                current_index INTEGER DEFAULT 0
            )
            ''')

            # Копіюємо тільки потрібні дані
            cursor.execute('''
            INSERT INTO users_new (user_id, words, current_index)
            SELECT user_id, words, current_index FROM users
            ''')

            # Видаляємо стару таблицю і перейменовуємо нову
            cursor.execute("DROP TABLE users")
            cursor.execute("ALTER TABLE users_new RENAME TO users")

            self.conn.commit()
        else:
            # Створюємо нову таблицю
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                words TEXT,
                current_index INTEGER DEFAULT 0
            )
            ''')
            self.conn.commit()

    def get_user_data(self, user_id):
        """Отримання даних користувача з БД"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user_record = cursor.fetchone()
        conn.close()

        if user_record:
            # Розпакування даних з БД
            user_id, words_json, current_index = user_record

            return {
                'words': json.loads(words_json),
                'current_index': current_index
            }
        else:
            # Користувача ще немає в БД
            return None

    def save_user_data(self, user_id, data):
        """Збереження даних користувача в БД"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        # Перетворюємо списки на JSON для зберігання
        words_json = json.dumps(data['words'])

        # Перевіряємо, чи існує вже запис для користувача
        cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
        user_exists = cursor.fetchone() is not None

        if user_exists:
            # Оновлюємо існуючий запис
            cursor.execute('''
            UPDATE users SET 
                words = ?,
                current_index = ?
            WHERE user_id = ?
            ''', (words_json, data['current_index'], user_id))
        else:
            # Створюємо новий запис
            cursor.execute('''
            INSERT INTO users 
                (user_id, words, current_index)
            VALUES (?, ?, ?)
            ''', (user_id, words_json, data['current_index']))

        conn.commit()
        conn.close()

    def close(self):
        """Закриття з'єднання з БД"""
        if self.conn:
            self.conn.close()
