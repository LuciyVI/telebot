import requests
from requests.auth import HTTPBasicAuth
import urllib3
import docker
import random
import time
import asyncio
import socket
import io

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import ParseMode, InputFile, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, ChatActions, PreCheckoutQuery

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta

import db  # Взаимодействие с базой данных
import backend  # Управление контейнерами и конфигурацией
import backup
# Отключение предупреждений urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Конфигурация
TOKEN = '7445572746:AAEOT9AhdvBuT1QyiEC90rVRfEMvBjbAmzI'  # Вставьте токен вашего бота
PROVIDER_TOKEN = '381764678:TEST:95954'  # Токен для платежей
CURRENCY = 'RUB'  # Валюта


bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Планировщик задач
scheduler = AsyncIOScheduler()
scheduler.start()


def main_menu(user_id: int):
    """
    Генерация главного меню.
    """
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💳 Купить конфиг", callback_data="buy_config"),
        InlineKeyboardButton("🎁 Попробуй бесплатно", callback_data="try_free")
    )
    markup.add(
        InlineKeyboardButton("ℹ️ FAQ", callback_data="faq"),
        InlineKeyboardButton("🛠 Поддержка", callback_data="support")
    )

    if db.is_admin(user_id):
        markup.add(InlineKeyboardButton("🔧 Админ-панель", callback_data="admin_panel"))

    return markup


@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    """
    Обработчик команды /start.
    """
    user_id = message.from_user.id
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=main_menu(user_id))

@dp.callback_query_handler(lambda c: c.data == "select_container_backup")
async def handle_select_container_backup(callback_query: types.CallbackQuery):
    """
    Выбор конкретного контейнера для бэкапа.
    """
    try:
        client = docker.from_env()
        containers = client.containers.list()
        markup = InlineKeyboardMarkup(row_width=1)

        # Используем сокращенные идентификаторы контейнеров
        for container in containers:
            # Укоротим callback_data до "backup_<короткий ID контейнера>"
            markup.add(InlineKeyboardButton(
                container.name, 
                callback_data=f"backup_{container.short_id}"
            ))

        markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_backups"))

        await callback_query.message.answer("Выберите контейнер для бэкапа:", reply_markup=markup)
    except Exception as e:
        print(f"Ошибка при выборе контейнера для бэкапа: {e}")
        await callback_query.message.answer("Произошла ошибка при загрузке списка контейнеров.")
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "buy_config")
async def send_payment_options(callback_query: types.CallbackQuery):
    """
    Обработчик кнопки "Купить конфиг".
    """
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💳 Юкасса", callback_data="pay_yookassa"),
        InlineKeyboardButton("🌟 Telegram Stars", callback_data="pay_stars")
    )
    await callback_query.message.answer("Выберите способ оплаты:", reply_markup=markup)
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "pay_yookassa")
async def send_yookassa_invoice(callback_query: types.CallbackQuery):
    """
    Обработчик оплаты через Юкасса.
    """
    prices = [LabeledPrice(label="Подписка на 1 месяц", amount=10000)]  # Цена в копейках
    await bot.send_invoice(
        chat_id=callback_query.message.chat.id,
        title="Подписка на сервис",
        description="Описание товара или услуги, например, подписка на 1 месяц",
        payload="subscription_payload",
        provider_token=PROVIDER_TOKEN,
        currency=CURRENCY,
        prices=prices,
        start_parameter="yookassa-payment"
    )
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "pay_stars")
async def send_stars_invoice(callback_query: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Оплатить", pay=True))

    title = "Подписка через Telegram Stars"
    prices = [LabeledPrice(label="XTR", amount=2)]

    await bot.send_invoice(
        chat_id=callback_query.from_user.id,
        title=title,
        description="Поддержка проекта через Telegram Stars",
        payload="channel_support",
        provider_token="",  # Telegram Stars не требует токена
        currency="XTR",
        prices=prices,
        reply_markup=keyboard
    )
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data in ["admin_create_container", "try_free"])
async def handle_create_container(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    command = callback_query.data  # Определяем, какая команда вызвана

    try:
        # Проверяем, является ли пользователь администратором
        is_admin = command == "admin_create_container" and db.is_admin(user_id)

        # Генерация уникальных параметров для контейнера
        container_suffix = random.randint(1, 100)
        port_443 = random.randint(5000, 6000)
        port_943 = random.randint(7000, 8000)
        port_1194_udp = random.randint(8000, 9000)

        # Запуск контейнера
        container = await backend.run_openvpn_container(container_suffix, port_443, port_943, port_1194_udp)
        if not container:
            await callback_query.message.answer("Ошибка при создании контейнера.")
            return

        # Получаем пароль из логов контейнера
        password = await backend.parse_container_logs_for_password(container.id)
        if not password:
            await callback_query.message.answer("Не удалось получить пароль контейнера.")
            return

        # Генерация конфигурации OpenVPN
        config = await backend.create_openvpn_config(container.id)
        if not config:
            await callback_query.message.answer("Ошибка при генерации конфигурации.")
            return

        # Настройка времени истечения доступа
        if is_admin:
            expiry_time = datetime.max  # Для администратора — без ограничения
            success_message = "Контейнер успешно создан. Конфигурация сгенерирована!"
        else:
            expiry_time = datetime.now() + timedelta(minutes=20)  # Пробный доступ — 20 минут
            success_message = "Пробный контейнер создан. Конфигурация сгенерирована на 20 минут."

        # Сохраняем данные о пользователе и контейнере в базу
        db.add_user(user_id, container.id, password, expiry_time.strftime('%Y-%m-%d %H:%M:%S'), config)

        # Планируем удаление контейнера для пробного доступа
        if not is_admin:
            scheduler.add_job(
                backend.delete_container,
                'date',
                run_date=expiry_time,
                args=[container.id, user_id]
            )

        # Отправляем конфигурацию пользователю
        await callback_query.message.answer_document(
            InputFile(io.BytesIO(config), filename="container.ovpn")
        )
        await callback_query.message.answer(success_message)
    except Exception as e:
        print(f"Error in handle_create_container: {e}")
        await callback_query.message.answer("Произошла ошибка. Попробуйте позже.")


@dp.callback_query_handler(lambda c: c.data == "admin_panel")
async def handle_admin_panel(callback_query: types.CallbackQuery):
    """
    Обработчик админ-панели.
    """
    user_id = callback_query.from_user.id
    if db.is_admin(user_id):
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton("🚀 Выпустить контейнер", callback_data="admin_create_container"),
            InlineKeyboardButton("🗂 Бекапы", callback_data="admin_backups"),
            InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")
        )
        await callback_query.message.answer("Админ-панель:", reply_markup=markup)
    else:
        await callback_query.message.answer("У вас нет прав доступа к админ-панели.")
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "admin_stats")
async def handle_admin_stats(callback_query: types.CallbackQuery):
    """
    Обработчик кнопки "Статистика" в админ-панели.
    """
    try:
        client = docker.from_env()
        containers = client.containers.list()

        stats_message = []
        for container in containers:
            # Получение общей информации о контейнере
            name = container.name
            status = container.status

            # Получение статистики по дисковому и сетевому использованию
            stats = container.stats(stream=False)
            disk_io = stats['blkio_stats']['io_service_bytes_recursive']
            disk_usage = sum(item['value'] for item in disk_io if 'value' in item)

            network_stats = stats['networks']
            network_usage = sum(interface['rx_bytes'] + interface['tx_bytes'] for interface in network_stats.values())

            stats_message.append(f"{name}:\n  Статус: {status}\n  Использование диска: {disk_usage} байт\n  Сетевая нагрузка: {network_usage} байт")

        if not stats_message:
            stats_message = ["Нет запущенных контейнеров."]

        await callback_query.message.answer("\n\n".join(stats_message))
    except Exception as e:
        print(f"Ошибка при получении статистики контейнеров: {e}")
        await callback_query.message.answer("Произошла ошибка при получении статистики.")
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "admin_backups")
async def handle_admin_backups(callback_query: types.CallbackQuery):
    """
    Обработчик кнопки "Бекапы" в админ-панели.
    """
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🔄 Восстановить все контейнеры", callback_data="restore_all_containers"),
        InlineKeyboardButton("💾 Забекапить все контейнеры", callback_data="backup_all_containers"),
        InlineKeyboardButton("📦 Выбрать контейнер для бэкапа", callback_data="select_container_backup"),
        InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel")
    )
    await callback_query.message.answer("Выберите действие с бэкапами:", reply_markup=markup)
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "restore_all_containers")
async def handle_restore_all_containers(callback_query: types.CallbackQuery):
    """
    Восстановление всех контейнеров.
    """
    try:
        # Здесь должна быть логика восстановления всех контейнеров
        await callback_query.message.answer("Все контейнеры успешно восстановлены.")
    except Exception as e:
        print(f"Ошибка при восстановлении контейнеров: {e}")
        await callback_query.message.answer("Произошла ошибка при восстановлении контейнеров.")
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "backup_all_containers")
async def handle_backup_all_containers(callback_query: types.CallbackQuery):
    """
    Создание бэкапов всех контейнеров.
    """
    try:
        backup_dir = "./backups"
        backup.backup_all_containers(backup_dir)
        await callback_query.message.answer("Бэкапы всех контейнеров успешно созданы.")
    except Exception as e:
        print(f"Ошибка при создании бэкапов: {e}")
        await callback_query.message.answer("Произошла ошибка при создании бэкапов.")
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("backup_"))
async def handle_backup_specific_container(callback_query: types.CallbackQuery):
    """
    Бэкап конкретного контейнера.
    """
    try:
        short_id = callback_query.data.split("backup_")[1]  # Извлечение короткого ID контейнера
        client = docker.from_env()
        
        # Поиск контейнера по короткому ID
        container = next((c for c in client.containers.list() if c.short_id == short_id), None)
        if not container:
            await callback_query.message.answer("Контейнер не найден.")
            return
        
        container_id = container.id  # Получение полного ID контейнера
        backup_dir = "./backups"
        
        # Логика бэкапа
        backup.backup_container(container_id, f"{backup_dir}/{container_id}_backup.tar")
        await callback_query.message.answer(f"Контейнер {container.name} успешно забекапен.")
    except Exception as e:
        print(f"Ошибка при бэкапе контейнера: {e}")
        await callback_query.message.answer("Произошла ошибка при создании бэкапа контейнера.")
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("backup_"))
async def handle_backup_specific_container(callback_query: types.CallbackQuery):
    """
    Бэкап конкретного контейнера.
    """
    try:
        short_id = callback_query.data.split("backup_")[1]  # Извлечение короткого ID контейнера
        container_id = backup.get_full_container_id(short_id)  # Замените на логику для получения полного ID, если требуется
        backup_dir = "./backups"
        backup.backup_container(container_id, f"{backup_dir}/{container_id}_backup.tar")
        await callback_query.message.answer(f"Контейнер {container_id} успешно забекапен.")
    except Exception as e:
        print(f"Ошибка при бэкапе контейнера {container_id}: {e}")
        await callback_query.message.answer("Произошла ошибка при создании бэкапа контейнера.")
    await callback_query.answer()

async def on_startup(dispatcher):
    """
    Инициализация при старте бота.
    """
    db.init_db()
    print("База данных инициализирована.")

@dp.pre_checkout_query_handler(lambda query: True)
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    
if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)
