import aiosqlite
import sqlite3

DATABASE = '/etc/scripts/bot_data.db'  # Укажите полный путь при необходимости


def init_db():
    """
    Инициализация базы данных. Создание таблиц, если они не существуют.
    """
    with sqlite3.connect(DATABASE) as conn:  # Автоматическое закрытие соединения
        cursor = conn.cursor()
        
        # Создание таблицы пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                container_id TEXT NOT NULL,
                password TEXT NOT NULL,
                expiry_time TEXT NOT NULL,
                config BLOB NOT NULL
            )
        ''')
        
        # Создание таблицы администраторов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                is_admin BOOLEAN NOT NULL
            )
        ''')
        
        # Добавление администратора, если он не существует
        cursor.execute('''
            INSERT OR IGNORE INTO admins (user_id, is_admin)
            VALUES (?, ?)
        ''', (139298351, True))
        cursor.execute('''
            INSERT OR IGNORE INTO admins (user_id, is_admin)
            VALUES (?, ?)
        ''', (1452759621, True))
        
        conn.commit()  # Сохраняем изменения


def add_user(user_id, container_id, password, expiry_time, config):
    """
    Добавляет пользователя в базу данных.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO users (user_id, container_id, password, expiry_time, config)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, container_id, password, expiry_time, config))
    
    conn.commit()
    conn.close()


def get_user(user_id):
    """
    Получает информацию о пользователе по user_id.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM users WHERE user_id = ?
    ''', (user_id,))
    
    user = cursor.fetchone()
    conn.close()
    return user


def update_user(user_id, container_id, password, expiry_time, config):
    """
    Обновляет данные пользователя.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users
        SET container_id = ?, password = ?, expiry_time = ?, config = ?
        WHERE user_id = ?
    ''', (container_id, password, expiry_time, config, user_id))
    
    conn.commit()
    conn.close()


def delete_user(user_id):
    """
    Удаляет пользователя из базы данных.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM users WHERE user_id = ?
    ''', (user_id,))
    
    conn.commit()
    conn.close()


def set_admin(user_id, is_admin=True):
    """
    Устанавливает статус администратора для пользователя.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO admins (user_id, is_admin)
        VALUES (?, ?)
    ''', (user_id, is_admin))
    
    conn.commit()
    conn.close()


def is_admin(user_id):
    """
    Проверяет, является ли пользователь администратором.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT is_admin FROM admins WHERE user_id = ?
    ''', (user_id,))
    
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else False


def get_all_users():
    """
    Возвращает список всех пользователей.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()
    conn.close()
    return users


def get_all_admins():
    """
    Возвращает список всех администраторов.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM admins WHERE is_admin = 1')
    admins = cursor.fetchall()
    conn.close()
    return admins