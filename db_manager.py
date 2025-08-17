import sqlite3
import json
import logging
from threading import Lock


class DatabaseManager:
    def __init__(self, db_name='words_bot.db'):
        self.db_name = db_name
        self.lock = Lock()  # Для thread-safety
        self.init_db()

    def init_db(self):
        """Ініціалізація бази даних"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()

            # Створюємо таблицю з правильною структурою
            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS users
                           (
                               user_id
                               INTEGER
                               PRIMARY
                               KEY,
                               words
                               TEXT
                               DEFAULT
                               '[]',
                               current_index
                               INTEGER
                               DEFAULT
                               0,
                               created_at
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP,
                               updated_at
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP
                           )
                           ''')

            # Створюємо індекс для швидшого пошуку
            cursor.execute('''
                           CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id)
                           ''')

            conn.commit()

    def get_user_data(self, user_id):
        """Отримання даних користувача з БД"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_name) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        'SELECT words, current_index FROM users WHERE user_id = ?',
                        (user_id,)
                    )
                    result = cursor.fetchone()

                    if result:
                        words_json, current_index = result
                        return {
                            'words': json.loads(words_json) if words_json else [],
                            'current_index': current_index or 0
                        }
                    return None
            except Exception as e:
                logging.error(f"Помилка при отриманні даних користувача {user_id}: {e}")
                return None

    def save_user_data(self, user_id, data):
        """Збереження даних користувача в БД"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_name) as conn:
                    cursor = conn.cursor()

                    words_json = json.dumps(data['words'], ensure_ascii=False)

                    cursor.execute('''
                    INSERT OR REPLACE INTO users 
                    (user_id, words, current_index, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (user_id, words_json, data['current_index']))

                    conn.commit()
            except Exception as e:
                logging.error(f"Помилка при збереженні даних користувача {user_id}: {e}")

    def get_user_count(self):
        """Отримати кількість користувачів"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            return cursor.fetchone()[0]

    def close(self):
        """Закриття з'єднання з БД"""
        # SQLite автоматично закриває з'єднання при використанні context manager
        pass