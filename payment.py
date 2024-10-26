from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import LabeledPrice

async def send_invoice(message: types.Message):
    # Устанавливаем параметры счета
    title = "Подписка на сервис"
    description = "Описание товара или услуги, например, подписка на 1 месяц"
    payload = "subscription_payload"  # Уникальный идентификатор для инвойса
    currency = "RUB"  # Код валюты
    prices = [LabeledPrice(label="Подписка на 1 месяц", amount=10000)]  # Цена в копейках (10000 = 100 рублей)

    # Отправка счета пользователю
    await bot.send_invoice(
        chat_id=message.chat.id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
        start_parameter="test-payment"
    )

@dp.pre_checkout_query_handler(lambda query: True)
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    # Подтверждаем предварительную проверку счета
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(message: types.Message):
    # Обработка успешного платежа
    await message.reply("Платеж успешно завершен! Спасибо за покупку.")
