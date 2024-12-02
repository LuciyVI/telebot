import requests
from requests.auth import HTTPBasicAuth
import urllib3
import docker
import random
import time

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import LabeledPrice

import re

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import ParseMode, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

import asyncio
import socket
import io

import db,backend

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN = ''  # Замените на ваш токен
PROVIDER_TOKEN = '381764678:TEST:95954'
CURRENCY='XTR'


bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Инициализация планировщика
scheduler = AsyncIOScheduler()
scheduler.start()

def get_unique_random_number_in_range(start, end):
    used_numbers = db.get_all_used_numbers()
    if len(used_numbers) >= (end - start + 1):
        raise ValueError("All possible numbers in the range have been used.")

    random_number = random.randint(start, end)

    while random_number in used_numbers:
        random_number = random.randint(start, end)

    db.add_used_number(random_number)
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
    

    # Schedule container access blocking after 20 minutes
    scheduler.add_job(
        block_container_access,
        'date',
        run_date=expiration_time,
        args=[container_id]
    )
    
def wait_for_port(port, host='0.0.0.0', timeout=60):
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
    """
    Создает меню с кнопками InlineKeyboardButton.
    """
    markup = InlineKeyboardMarkup(row_width=2)
    btn1 = InlineKeyboardButton("💳 Купить конфиг", callback_data="buy_config")
    btn2 = InlineKeyboardButton("🎁 Попробуй бесплатно", callback_data="try_free")
    btn3 = InlineKeyboardButton("ℹ️ FAQ", callback_data="faq")
    btn4 = InlineKeyboardButton("🛠 Поддержка", callback_data="support")
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    return markup

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.answer("Welcome! Please choose an action:", reply_markup=main_menu())


# Добавьте токен для Telegram Stars


@dp.callback_query_handler(lambda c: c.data == "buy_config")
async def send_invoice(callback_query: types.CallbackQuery):
    """
    Обработчик кнопки "Купить конфиг" с выбором способа оплаты.
    """
    # Создаем клавиатуру для выбора способа оплаты
    markup = InlineKeyboardMarkup(row_width=2)
    btn_yookassa = InlineKeyboardButton("💳 Юкасса", callback_data="pay_yookassa")
    btn_stars = InlineKeyboardButton("🌟 Telegram Stars", callback_data="pay_stars")
    markup.add(btn_yookassa, btn_stars)

    await callback_query.message.answer(
        "Выберите способ оплаты:", 
        reply_markup=markup
    )
    await callback_query.answer()  # Закрываем уведомление о нажатии кнопки


@dp.callback_query_handler(lambda c: c.data == "pay_yookassa")
async def send_yookassa_invoice(callback_query: types.CallbackQuery):
    """
    Обработчик для оплаты через Юкасса.
    """
    title = "Подписка на сервис"
    description = "Описание товара или услуги, например, подписка на 1 месяц"
    payload = "subscription_payload"  # Уникальный идентификатор для инвойса
    currency = "RUB"  # Код валюты
    prices = [LabeledPrice(label="Подписка на 1 месяц", amount=10000)]  # Цена в копейках (10000 = 100 рублей)

    await bot.send_invoice(
        chat_id=callback_query.message.chat.id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=CURRENCY,
        prices=prices,
        start_parameter="yookassa-payment"
    )
    await callback_query.answer()  # Закрываем уведомление о нажатии кнопки


@dp.callback_query_handler(lambda c: c.data == "pay_stars")
async def send_stars_invoice(callback_query: types.CallbackQuery):
    """
    Обработчик для оплаты через Telegram Stars.
    """
    # Создаем клавиатуру
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Оплатить", pay=True))  # Кнопка с функцией оплаты

    title = "Подписка через Telegram Stars"
    prices = [LabeledPrice(label="XTR", amount=2000)]  # Сумма указывается в копейках/центах (XTR * 100)
    await bot.send_invoice(
        chat_id=callback_query.from_user.id,  # Отправляем счет пользователю
        title=title,
        description="Поддержать канал на 20 звёзд!",
        payload="channel_support",
        provider_token="",  # Укажите ваш токен платежного провайдера
        currency="XTR",
        prices=prices,
        reply_markup=keyboard,  # Указываем клавиатуру
    )
    await callback_query.answer()  # Закрываем уведомление о нажатии кнопки

@dp.pre_checkout_query_handler(lambda query: True)
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    # Подтверждаем предоплату
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    

@dp.callback_query_handler(lambda c: c.data == "try_free")
async def handle_trial(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id  # Получаем ID пользователя из callback_query

    if db.has_used_trial(user_id):
        # Пользователь уже использовал бесплатный конфиг
        user_config = db.get_user_config(user_id)
        if user_config:
            await callback_query.message.answer_document(InputFile(io.BytesIO(user_config), filename="trial.ovpn"))
        else:
            await callback_query.message.answer("Ошибка при получении вашего конфига.")
    else:
        try:
            container_suffix = get_unique_random_number_in_range(1, 100)
            port_443 = get_unique_random_number_in_range(5000, 6000)
            port_943 = get_unique_random_number_in_range(7000, 8000)
            port_1194_udp = get_unique_random_number_in_range(8000, 9000)

            # Создаем контейнер
            container = await backend.run_openvpn_container(container_suffix, port_443, port_943, port_1194_udp)
            if container is None:
                await callback_query.message.answer("Произошла ошибка. Повторите попытку позже или обратитесь в поддержку.")
                return

            container_id = container.short_id

            # Планируем удаление контейнера через 20 минут
            scheduler.add_job(
                backend.delete_container, 
                'date', 
                run_date=datetime.now() + timedelta(minutes=20), 
                args=[container_id, user_id]
            )

            # Генерация OpenVPN-конфига
            config = await backend.create_openvpn_config(container_id)
            if config is None:
                await callback_query.message.answer("Произошла ошибка. Повторите попытку позже или обратитесь в поддержку.")
                return

            # Сохраняем данные о пользователе в БД
            db.add_user(user_id, container_id, datetime.now() + timedelta(minutes=20), config)

            # Отправляем конфиг пользователю
            await callback_query.message.answer_document(InputFile(io.BytesIO(config), filename="trial.ovpn"))
            await callback_query.message.answer("Попробуйте наш пробный доступ в течение 20 минут.")
        except Exception as e:
            print(f"Error creating container: {e}")
            await callback_query.message.answer("Произошла ошибка при создании контейнера.")
    await callback_query.answer()  # Закрываем уведомление о нажатии кнопки

    
@dp.callback_query_handler(lambda c: c.data == "faq")
async def handle_faq(callback_query: types.CallbackQuery):
    """
    Обработчик кнопки "ℹ️ FAQ".
    """
    faq_text = """
    ❓ FAQ:
    1. Как настроить наш VPN на телефоне?
       - Скачайте приложение OpenVPN на ваше мобильное устройство из Google Play или App Store:
         https://apps.apple.com/ru/app/openvpn-connect-openvpn-app/id590379981
         https://play.google.com/store/apps/developer?id=OpenVPN
       - Импортируйте конфиг в приложение и подключитесь.

    2. Можно ли настроить наш VPN на роутере?
       - Да, наш сервис поддерживает настройку на роутерах Keenetic.

    3. Сколько стоит наш VPN?
       - 1 месяц: 300 рублей.
       - 6 месяцев: 1700 рублей.
       - 1 год: 3450 рублей.

    4. Есть ли бесплатный пробный период?
       - Да, вы можете получить бесплатный доступ на 20 минут.
    """
    await callback_query.message.answer(faq_text)  # Используем callback_query.message.answer()
    await callback_query.answer()  # Закрываем уведомление



@dp.callback_query_handler(lambda c: c.data == "support")
async def handle_support(callback_query: types.CallbackQuery):
    """
    Обработчик кнопки "Поддержка".
    """
    support_text = "Если возникли проблемы, напишите в поддержку: @PerryPetr"
    await callback_query.message.answer(support_text)  # Используем callback_query.message.answer()
    await callback_query.answer()  # Закрываем уведомление


if __name__ == "__main__":
    db.init_db()
    executor.start_polling(dp)
