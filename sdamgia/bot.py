import asyncio
import random
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile
)
from aiogram.filters import Command
from sdamgia import SdamGIA
import os

# Включаем логирование, чтобы видеть в консоли всё, что происходит
logging.basicConfig(level=logging.INFO)

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8728610736:AAHqbVG688xdQ0E8osjWuMNfiu2UruxnC2o"

# Инициализируем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Настраиваем API СдамГИА для ОГЭ по информатике
sdamgia = SdamGIA()
sdamgia._SUBJECT_BASE_URL['inf'] = 'https://inf-oge.sdamgia.ru'

# --- МАТЕРИАЛЫ С ВИДЕО ---
# Папка videos должна лежать рядом с bot.py
# Пример:
# videos/task1.mp4
# videos/task2.mp4
# ...
# videos/task12.mp4

# Если бот лежит в sdamgia-api-master, путь должен быть таким:
# Получаем полный путь к папке, в которой лежит текущий файл (bot.py)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

MATERIALS = {
    str(i): {
        # Склеиваем путь к папке бота и папке видео
        "video_path": os.path.join(CURRENT_DIR, "videos", f"task{i}.mp4"),
        "caption": f"Краткий материал по заданию №{i}.\n\nПосле просмотра нажми кнопку «Показать задание 📘»."
    }
    for i in range(1, 13)
}


# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================

def get_start_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с номерами заданий"""
    buttons = []
    for i in range(1, 13):
        buttons.append(
            InlineKeyboardButton(text=f"№{i}", callback_data=f"task_{i}")
        )

    keyboard = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_material_choice_keyboard(task_number: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора: отправить материал или нет"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да", callback_data=f"material_yes_{task_number}"),
                InlineKeyboardButton(text="Нет", callback_data=f"material_no_{task_number}")
            ]
        ]
    )


def get_show_task_keyboard(task_number: str) -> InlineKeyboardMarkup:
    """Кнопка показать задание после видео"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Показать задание 📘",
                    callback_data=f"show_task_{task_number}"
                )
            ]
        ]
    )


def get_answer_keyboard(problem_id: str) -> InlineKeyboardMarkup:
    """Кнопка показать ответ"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Показать ответ 👀",
                    callback_data=f"ans_{problem_id}"
                )
            ]
        ]
    )


def load_task(task_number: str):
    """
    Загружает случайное задание по номеру.
    Возвращает:
    task_text, answer_keyboard, image_url
    """

    # Получаем каталог тем
    catalog = sdamgia.get_catalog('inf')

    # Ищем тему с нужным номером задания
    target_topic = None
    for topic in catalog:
        if str(topic['topic_id']) == str(task_number):
            target_topic = topic
            break

    if not target_topic:
        raise Exception(f"Не удалось найти раздел для задания №{task_number}")

    # Ищем непустую категорию внутри задания
    problem_ids = []
    attempts = 0

    while not problem_ids and attempts < 10:
        random_category = random.choice(target_topic['categories'])
        problem_ids = sdamgia.get_category_by_id(
            'inf',
            random_category['category_id'],
            page=1
        )
        attempts += 1

    if not problem_ids:
        raise Exception("В этом задании сейчас нет доступных задач")

    # Выбираем случайную задачу
    random_problem_id = random.choice(problem_ids)
    problem = sdamgia.get_problem_by_id('inf', random_problem_id)

    # Формируем текст задания
    task_text = f"<b>Задание {task_number}:</b> {target_topic['topic_name']}\n\n"
    task_text += problem['condition']['text']

    # Если есть картинка
    image_url = None
    if problem['condition'].get('images'):
        images = problem['condition']['images']
        if images:
            image_url = images[0]

    return task_text, get_answer_keyboard(str(random_problem_id)), image_url


async def send_task(callback: CallbackQuery, task_number: str):
    """Отправляет само задание"""
    wait_msg = await callback.message.answer(
        f"Ищу задание №{task_number}, подожди секунду..."
    )

    try:
        # Получаем задание
        task_text, answer_keyboard, image_url = load_task(task_number)

        # Удаляем служебное сообщение
        await wait_msg.delete()

        # Отправляем текст задания
        await callback.message.answer(
            task_text,
            reply_markup=answer_keyboard,
            parse_mode="HTML"
        )

        # Если есть картинка — отправляем как фото
        if image_url:
            await callback.message.answer_photo(photo=image_url)

    except Exception as e:
        await wait_msg.edit_text(
            "Упс, что-то пошло не так при поиске задачи. Попробуй ещё раз!"
        )
        print(f"Ошибка при поиске задачи: {e}")


# =========================
# ЛОГИКА БОТА
# =========================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Срабатывает при команде /start и выводит меню выбора задания"""
    await message.answer(
        "Привет! Я бот-решебник по ОГЭ Информатика.\n"
        "Выбери номер задания (часть 1), которое хочешь потренировать:",
        reply_markup=get_start_keyboard(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("task_"))
async def ask_about_material(callback: CallbackQuery):
    """После выбора задания спрашиваем, отправить ли сжатый материал"""
    task_number = callback.data.split("_")[1]

    await callback.answer()

    await callback.message.answer(
        f"Для задания №{task_number} сначала отправить сжатый материал?",
        reply_markup=get_material_choice_keyboard(task_number)
    )


@dp.callback_query(F.data.startswith("material_no_"))
async def send_task_directly(callback: CallbackQuery):
    """Если пользователь выбрал 'Нет' — сразу отправляем задание"""
    task_number = callback.data.split("_")[2]

    await callback.answer()
    await send_task(callback, task_number)


@dp.callback_query(F.data.startswith("material_yes_"))
async def send_material_video(callback: CallbackQuery):
    """Если пользователь выбрал 'Да' — отправляем видео и кнопку 'Показать задание'"""
    task_number = callback.data.split("_")[2]

    await callback.answer()

    material = MATERIALS.get(task_number)

    if not material:
        await callback.message.answer(
            "Для этого задания пока нет сжатого материала. Сразу отправляю задание."
        )
        await send_task(callback, task_number)
        return

    try:
        video = FSInputFile(material["video_path"])

        await callback.message.answer_video(
            video=video,
            caption=material["caption"],
            reply_markup=get_show_task_keyboard(task_number)
        )

    except FileNotFoundError:
        await callback.message.answer(
            "Видео для этого задания не найдено. Сразу отправляю задание."
        )
        await send_task(callback, task_number)

    except Exception as e:
        await callback.message.answer(
            "Не удалось отправить видео с материалом. Сразу отправляю задание."
        )
        print(f"Ошибка при отправке видео: {e}")
        await send_task(callback, task_number)


@dp.callback_query(F.data.startswith("show_task_"))
async def show_task_after_video(callback: CallbackQuery):
    """После видео отправляем само задание"""
    task_number = callback.data.split("_")[2]

    await callback.answer()
    await send_task(callback, task_number)


@dp.callback_query(F.data.startswith("ans_"))
async def show_answer(callback: CallbackQuery):
    """Срабатывает при нажатии на кнопку 'Показать ответ'"""
    problem_id = callback.data.split("_")[1]

    try:
        problem = sdamgia.get_problem_by_id('inf', problem_id)

        answer_text = problem.get('answer', 'Ответ не найден')
        solution_text = problem.get('solution', {}).get('text', 'Решения нет')

        text = f"<b>Правильный ответ:</b> {answer_text}\n\n"
        text += f"<b>Решение:</b>\n{solution_text}"

        await callback.message.answer(text, parse_mode="HTML")

    except Exception as e:
        await callback.message.answer("Не удалось получить ответ. Попробуй ещё раз.")
        print(f"Ошибка при получении ответа: {e}")

    await callback.answer()


# =========================
# ЗАПУСК БОТА
# =========================

async def main():
    print("Бот успешно запущен и готов к работе!")

    try:
        # Сбрасываем старые обновления
        await bot.delete_webhook(drop_pending_updates=True)

        # Запускаем постоянный опрос серверов Telegram
        await dp.start_polling(bot)

    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен вручную.")