import requests
from requests.auth import HTTPBasicAuth
import urllib3
import docker
import random
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

TOKEN = '7445572746:AAEOT9AhdvBuT1QyiEC90rVRfEMvBjbAmzI'  # Replace with your token
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Path to the SQLite database file
DATABASE = '/etc/scripts/bot_data.db'  # Specify full path if necessary

# Scheduler initialization
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
            expiry_time DATETIME NOT NULL
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

def add_user(user_id, container_id, expiry_time):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (user_id, container_id, expiry_time) VALUES (?, ?, ?)
    ''', (user_id, container_id, expiry_time))
    conn.commit()
    conn.close()

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

def get_unique_random_number_in_range(start, end):
    used_numbers = get_all_used_numbers()
    if len(used_numbers) >= (end - start + 1):
        raise ValueError("All possible numbers in the range have been used.")
    
    random_number = random.randint(start, end)
    
    while random_number in used_numbers:
        random_number = random.randint(start, end)
    
    add_used_number(random_number)
    return random_number

async def run_openvpn_container(container_suffix, port_443, port_943, port_1194_udp):
    client = docker.from_env()
    container_name = f"openvpn-as{container_suffix}"
    volume_path = f"/etc/openvpn{container_suffix}"

    try:
        container = client.containers.run(
            image="b0721bd08080",  # Replace with actual container image
            name=container_name,
            cap_add=["NET_ADMIN"],
            detach=True,
            ports={
                f'{443}/tcp': port_443,
                f'{943}/tcp': port_943,
                f'{1194}/udp': port_1194_udp
            },
            volumes={
                volume_path: {'bind': '/openvpn', 'mode': 'rw'}
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

async def parse_container_logs_for_password(container_id):
    client = docker.from_env()
    
    try:
        container = client.containers.get(container_id)
        logs = container.logs().decode('utf-8')

        password_match = re.search(r'Auto-generated pass = "(.+?)"', logs)

        if password_match:
            return password_match.group(1)
        else:
            return "No matching password found in the container logs."
    except docker.errors.NotFound:
        return f"Container {container_id} not found."
    except Exception as e:
        return f"Error occurred: {str(e)}"

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

    if user_exists(user_id):
        await message.answer("You have already used the free trial config.")
        return

    container_id = None

    try:
        container_suffix = get_unique_random_number_in_range(1, 100)
        port_443 = get_unique_random_number_in_range(5000, 6000)
        port_943 = get_unique_random_number_in_range(7000, 8000)
        port_1194_udp = get_unique_random_number_in_range(8000, 9000)
        
        container = await run_openvpn_container(container_suffix, port_443, port_943, port_1194_udp)
        container_id = container.short_id
        
        config = await create_openvpn_config(trial=True)
        await message.answer_document(InputFile(io.BytesIO(config), filename="trial.ovpn"))

        expiry_time = datetime.now() + timedelta(hours=24)
        add_user(user_id, container_id, expiry_time)

    except Exception as e:
        print(f"Error creating container: {e}")
        await message.answer("An error occurred while creating the container.")
        return

    if container_id:
        await message.answer(f"Your free trial config has been created. Container ID: {container_id}")
    else:
        await message.answer("Failed to create the container.")

@dp.message_handler(lambda message: message.text == "ℹ️ FAQ")
async def handle_faq(message: types.Message):
    faq_text = """
    ❓ FAQ:
    1. How do I set up OpenVPN?
    - Download the config to your device or router and connect to the VPN.

    2. How much does the config cost?
    - Please check the current pricing on our website or contact support.

    3. Is there a free trial?
    - Yes, you can get a free trial config.
    """
    await message.answer(faq_text)

@dp.message_handler(lambda message: message.text == "🛠 Support")
async def handle_support(message: types.Message):
    support_text = "Contact our support at this email: support@example.com"
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
if __name__ == "__main__":
    init_db()
    executor.start_polling(dp)
