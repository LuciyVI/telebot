import sqlite3

DATABASE = '/etc/scripts/bot_data.db'  # Укажите полный путь при необходимости

def init_db():
    print("Initializing database...")
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            container_id TEXT NOT NULL,
            expiry_time DATETIME NOT NULL,
            config BLOB,
            used_trial BOOLEAN DEFAULT 0  -- Новое поле для отметки использования бесплатного конфига
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS used_numbers (
            number INTEGER PRIMARY KEY
        )
    ''')

    conn.commit()
    conn.close()
    print("Database initialized.")

def add_user(user_id, container_id, expiry_time, config):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (user_id, container_id, expiry_time, config, used_trial) VALUES (?, ?, ?, ?, ?)
    ''', (user_id, container_id, expiry_time, config, True))  # Устанавливаем used_trial в True
    conn.commit()
    conn.close()

def has_used_trial(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT used_trial FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0] == 1
    else:
        return False

def user_exists(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def remove_user(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def add_used_number(number):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO used_numbers (number) VALUES (?)
    ''', (number,))
    conn.commit()
    conn.close()

def is_number_used(number):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM used_numbers WHERE number = ?', (number,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def get_all_used_numbers():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT number FROM used_numbers')
    numbers = cursor.fetchall()
    conn.close()
    return [num[0] for num in numbers]

def get_user_config(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT config FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0]
    else:
        return None
