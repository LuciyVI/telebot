from aiogram import Bot, Dispatcher, types
from aiogram.types import LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton

PROVIDER_TOKEN = "381764678:TEST:95954"  # Токен для Юкасса
STARS_PROVIDER_TOKEN = ""  # Замените на токен Telegram Stars

async def send_payment_choice(message: types.Message):
    """
    Отправка пользователю выбора способа оплаты.
    """
    markup = InlineKeyboardMarkup(row_width=1)
    btn_yookassa = InlineKeyboardButton(text="💳 Оплата через Юкасса", callback_data="pay_yookassa")
    btn_stars = InlineKeyboardButton(text="🌟 Оплата через Telegram Stars", callback_data="pay_stars")
    markup.add(btn_yookassa, btn_stars)
    
    await message.answer("Выберите способ оплаты:", reply_markup=markup)

async def send_yookassa_invoice(message: types.Message):
    """
    Отправка инвойса для оплаты через Юкасса.
    """
    title = "Подписка на сервис"
    description = "Подписка на 1 месяц"
    payload = "subscription_payload"
    currency = "RUB"
    prices = [LabeledPrice(label="Подписка на 1 месяц", amount=10000)]  # Цена в копейках (10000 = 100 рублей)

    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
        start_parameter="test-payment"
    )

async def send_stars_invoice(message: types.Message):
    """
    Отправка инвойса для оплаты через Telegram Stars.
    """
    title = "Подписка через Telegram Stars"
    description = "Подписка на 1 месяц через Telegram Stars"
    payload = "stars_subscription_payload"
    currency = "RUB"
    prices = [LabeledPrice(label="Подписка на 1 месяц", amount=10000)]  # Цена в копейках (10000 = 100 рублей)

    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",
        currency=currency,
        prices=prices,
        start_parameter="telegram-stars-payment"
    )

async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    """
    Подтверждение предоплаты.
    """
    await pre_checkout_query.bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

async def successful_payment(message: types.Message):
    """
    Обработка успешного платежа.
    """
    await message.reply("Платеж успешно завершен! Спасибо за покупку.")
