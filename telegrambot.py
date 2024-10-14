import requests
from requests.auth import HTTPBasicAuth
import urllib3
import docker
import random
import time

import re
import sqlite3
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import ParseMode, InputFile
from aiogram.utils import executor

import asyncio
import socket
import io

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN = '7445572746:AAEOT9AhdvBuT1QyiEC90rVRfEMvBjbAmzI'  # Замените на ваш токен
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Путь к файлу базы данных SQLite
DATABASE = '/etc/scripts/bot_data.db'  # Укажите полный путь при необходимости

# Инициализация планировщика
scheduler = AsyncIOScheduler()
scheduler.start()

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

def user_exists(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

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

def get_user_container_id(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT container_id FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0]
    else:
        return None

def remove_user(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def user_has_trial(user_id,container_id, expiration_time_str, config, is_paid):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (
            user_id, container_id, expiration_time, config, is_paid, has_used_trial
        )
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, container_id, expiration_time_str, config, is_paid, has_used_trial))
    conn.commit()

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

def get_unique_random_number_in_range(start, end):
    used_numbers = get_all_used_numbers()
    if len(used_numbers) >= (end - start + 1):
        raise ValueError("All possible numbers in the range have been used.")

    random_number = random.randint(start, end)

    while random_number in used_numbers:
        random_number = random.randint(start, end)

    add_used_number(random_number)
    return random_number

def add_trial_user(user_id, container_id, config):
    """
    Adds a trial user to the database with a 20-minute expiration time.

    Args:
        user_id (int): The Telegram user ID.
        container_id (str): The ID of the Docker container associated with the user.
        config (bytes): The OpenVPN configuration file as bytes.
    """
    expiration_time = datetime.now() + timedelta(minutes=20)
    expiration_time_str = expiration_time.strftime('%Y-%m-%d %H:%M:%S')
    has_used_trial = 1
    is_paid = 0
    user_has_trial(user_id, container_id, expiration_time_str, config, is_paid)

    # Schedule container access blocking after 20 minutes
    scheduler.add_job(
        block_container_access,
        'date',
        run_date=expiration_time,
        args=[container_id]
    )

async def run_openvpn_container(container_suffix, port_443, port_943, port_1194_udp):
    client = docker.from_env()
    container_name = f"openvpn-as{container_suffix}"
    volume_path = f"/etc/openvpn{container_suffix}"  # Убедитесь, что этот путь доступен для записи

    try:
        container = client.containers.run(
            image="openvpn/openvpn-as",  # Используйте актуальный образ
            name=container_name,
            cap_add=["NET_ADMIN"],
            detach=True,
            ports={
                f'{443}/tcp': port_443,
                f'{943}/tcp': port_943,
                f'{1194}/udp': port_1194_udp
            },
            volumes={
                volume_path: {'bind': '/etc/openvpn', 'mode': 'rw'}
            }
        )
        print(f"Container {container_name} started.")
        return container
    except docker.errors.ContainerError as e:
        print(f"Container error: {e}")
    except docker.errors.ImageNotFound as e:
        print(f"Image not found: {e}")
    except docker.errors.APIError as e:
        print(f"Docker API error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return None

async def parse_container_logs_for_password(container_id):
    client = docker.from_env()

    try:
        container = client.containers.get(container_id)
        logs = container.logs().decode('utf-8')

        password_match = re.search(r'Admin UI Password: (.+)', logs)

        if password_match:
            return password_match.group(1).strip()
        else:
            return "No matching password found in the container logs."
    except docker.errors.NotFound:
        return f"Container {container_id} not found."
    except Exception as e:
        return f"Error occurred: {str(e)}"
    
def wait_for_port(port, host='localhost', timeout=60):
    start_time = time.time()
    while True:
        try:
            with socket.create_connection((host, port), timeout=5):
                return True
        except OSError:
            time.sleep(1)
            if time.time() - start_time >= timeout:
                return False
async def get_running_containers_info(type_info):
    client = docker.from_env()
    containers_info = []

    containers = client.containers.list()

    for container in containers:
        container_data = {
            'id': container.short_id,
            'name': container.name,
            'ports': container.ports,
            'status': container.status,
            'image': container.image.tags
        }

        if type_info in container_data:
            containers_info.append(container_data[type_info])
        else:
            containers_info.append(None)

    return containers_info

def block_container_access(container_id):
    client = docker.from_env()
    try:
        container = client.containers.get(container_id)
        container.stop()
        # Update the database to indicate that access has been blocked
        conn = sqlite3.connect(DATABASE)
        conn.execute('''
            UPDATE users SET access_blocked = 1 WHERE container_id = ?
        ''', (container_id,))
        conn.commit()
        print(f"Access to container {container_id} has been blocked after the trial period.")
    except Exception as e:
        print(f"Error stopping container {container_id}: {e}")



def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("💳 Buy config")
    btn2 = types.KeyboardButton("🎁 Free trial config")
    btn3 = types.KeyboardButton("ℹ️ FAQ")
    btn4 = types.KeyboardButton("🛠 Support")
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    return markup

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.answer("Welcome! Please choose an action:", reply_markup=main_menu())

@dp.message_handler(lambda message: message.text == "💳 Buy config")
async def handle_buy(message: types.Message):
    await message.answer("To purchase a config, please make a payment via the provided link.")

@dp.message_handler(lambda message: message.text == "🎁 Free trial config")
async def handle_trial(message: types.Message):
    user_id = message.chat.id

    if has_used_trial(user_id):
        # Пользователь уже использовал бесплатный конфиг
        await message.answer("Вы уже использовали бесплатный пробный конфиг. Отправляю ваш ранее выданный конфиг.")
        user_config = get_user_config(user_id)
        if user_config:
            await message.answer_document(InputFile(io.BytesIO(user_config), filename="trial.ovpn"))
        else:
            await message.answer("Ошибка при получении вашего конфига.")
        return
    # container_id = None
    

    try:
        container_suffix = get_unique_random_number_in_range(1, 1000)
        port_443 = get_unique_random_number_in_range(5000, 6000)
        port_943 = get_unique_random_number_in_range(7000, 8000)
        port_1194_udp = get_unique_random_number_in_range(8000, 9000)
        
        container = await run_openvpn_container(container_suffix, port_443, port_943, port_1194_udp)
        if container is None:
            await message.answer("Failed to create container. Please try again later.")
            return

        container_id = container.short_id

        # Schedule container deletion after 20 minutes
        scheduler.add_job(delete_container, 'date', run_date=datetime.now() + timedelta(minutes=20), args=[container_id, user_id])

        # Wait for the container service to start
        # await asyncio.sleep(15)  # Adjust as necessary

        config = await create_openvpn_config(container_id)
        if config is None:
            await message.answer("Error generating configuration. Please try again later.")
            return

        # Save the config in the database and mark the user as having used the free config
        add_user(user_id, container_id, datetime.now() + timedelta(minutes=20), config)

        await message.answer_document(InputFile(io.BytesIO(config), filename="trial.ovpn"))
        await message.answer("Your free trial config has been created and will be valid for 20 minutes.")
    
    except Exception as e:
        print(f"Error creating container: {e}")
        await message.answer("An error occurred while creating the container.")
        return

    
@dp.message_handler(lambda message: message.text == "ℹ️ FAQ")
async def handle_faq(message: types.Message):
    faq_text = """
    ❓ FAQ:
    1. Как настроить OpenVPN?
    - Скачайте конфиг на ваше устройство или роутер и подключитесь к VPN.

    2. Сколько стоит конфиг?
    - Пожалуйста, ознакомьтесь с актуальными ценами на нашем сайте или свяжитесь со службой поддержки.

    3. Есть ли бесплатный пробный период?
    - Да, вы можете получить бесплатный пробный конфиг.
    """
    await message.answer(faq_text)

async def handle_support(message: types.Message):
    support_text = "Свяжитесь с нашей поддержкой по электронной почте: support@example.com"
    await message.answer(support_text)

async def create_openvpn_config(trial=False):
    """
    Генерация OpenVPN конфигурации с подстановкой корректных портов и IP-адресов.
    Включает аутентификацию с использованием имени пользователя и пароля, получаемого из логов контейнера.
    """
    client = docker.from_env()

    # Получаем ID последнего запущенного контейнера
    container_id = (await get_running_containers_info('id'))[-1]
    container = client.containers.get(container_id)

    # Получаем информацию о портах контейнера
    container_ports = container.attrs['NetworkSettings']['Ports']
    
    # Получаем значение внешнего UDP порта
    internal_port_udp = f"{1194}/udp"
    connect_port_udp = container_ports.get(internal_port_udp, [])
    connect_port_udp_value = connect_port_udp[0]['HostPort'] if connect_port_udp else None

    # Получаем значение внешнего TCP порта
    internal_port_tcp = f"{443}/tcp"
    connect_port_tcp = container_ports.get(internal_port_tcp, [])
    connect_port_tcp_value = connect_port_tcp[0]['HostPort'] if connect_port_tcp else None
    
    # Внутренний IP адрес контейнера
    internal_ip = container.attrs['NetworkSettings']['IPAddress']

    # URL для обращения к контейнеру по API
    url = f'https://0.0.0.0:{connect_port_tcp_value}/rest/GetGeneric'
    
    # Дефолтное имя пользователя OpenVPN
    username = 'openvpn'
    
    # Получаем автоматически сгенерированный пароль из логов контейнера
    password = await parse_container_logs_for_password(container_id)

    # Выполняем запрос к API контейнера для получения исходной конфигурации
    response = requests.get(url, auth=HTTPBasicAuth(username, password), verify=False)
    payload = response.content.decode('utf-8')

    # Заменяем внутренний IP контейнера на внешний IP сервера
    modified_payload = payload.replace(internal_ip, '109.120.179.155')
    
    # Подставляем внешние порты
    if connect_port_udp_value:
        modified_payload = modified_payload.replace('1194', connect_port_udp_value)
    if connect_port_tcp_value:
        modified_payload = modified_payload.replace('443', connect_port_tcp_value)

    # Очищаем конфигурацию от комментариев и ненужных строк
    cleaned_payload = '\n'.join([line for line in modified_payload.splitlines() if not line.strip().startswith('#')])

    # Убираем строку "auth-user-pass" из конфигурации
    cleaned_payload = re.sub(r'auth-user-pass', '', cleaned_payload, flags=re.DOTALL)

    # Добавляем секцию с аутентификацией
    auth_user_pass = f"""
pull-filter ignore "dhcp-pre-release"
pull-filter ignore "dhcp-renew"
pull-filter ignore "dhcp-release"
pull-filter ignore "register-dns"
pull-filter ignore "block-ipv6"
<auth-user-pass>
openvpn
{password}
</auth-user-pass>
"""
    
    # Формируем финальную конфигурацию
    final_payload = cleaned_payload + "\n" + auth_user_pass.strip()
    
    # Кодируем строку в байты для отправки как файл
    encoded_payload = final_payload.encode('utf-8')
    return encoded_payload

async def delete_container(container_id, user_id):
    client = docker.from_env()
    try:
        container = client.containers.get(container_id)
        container.stop()
        container.remove()
        print(f"Container {container_id} has been deleted after 20 minutes.")
        # Удаляем пользователя из базы данных
        remove_user(user_id)
    except docker.errors.NotFound:
        print(f"Container {container_id} not found for deletion.")
    except Exception as e:
        print(f"Error deleting container {container_id}: {str(e)}")

if __name__ == "__main__":
    init_db()
    executor.start_polling(dp)
