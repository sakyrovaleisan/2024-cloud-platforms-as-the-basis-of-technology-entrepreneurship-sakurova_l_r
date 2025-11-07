"""Telegram feedback bot using python-telegram-bot.

This bot collects feedback from users, stores it in a JSON file, keeps
simple statistics, and provides admin-only commands for exporting and
clearing the stored data.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from telegram import Message, Update
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# Conversation states
AWAITING_FEEDBACK_TEXT = 1


@dataclass
class FeedbackEntry:
    """Represents a single feedback item."""

    user_id: int
    username: str | None
    full_name: str | None
    text: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "full_name": self.full_name,
            "text": self.text,
            "timestamp": self.timestamp,
        }


@dataclass
class Employee:
    """Describe a single employee record from the CSV file."""

    name: str
    department: str
    role: str
    email: str

    def formatted(self) -> str:
        return (
            f"Имя: {self.name}\n"
            f"Отдел: {self.department}\n"
            f"Роль: {self.role}\n"
            f"Email: {self.email}"
        )


class FeedbackStorage:
    """JSON-backed storage for feedback with simple statistics."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._lock = asyncio.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self.file_path.exists():
            logging.info("Creating storage file at %s", self.file_path)
            self.file_path.write_text(
                json.dumps(
                    {
                        "feedback": [],
                        "stats": {
                            "total_messages": 0,
                            "user_message_counts": {},
                        },
                    },
                    indent=2,
                )
            )

    async def _read(self) -> Dict[str, Any]:
        async with self._lock:
            try:
                data = json.loads(self.file_path.read_text())
            except json.JSONDecodeError as exc:
                logging.error("Failed to read storage JSON: %s", exc)
                data = {
                    "feedback": [],
                    "stats": {
                        "total_messages": 0,
                        "user_message_counts": {},
                    },
                }
                self.file_path.write_text(json.dumps(data, indent=2))
            return data

    async def _write(self, data: Dict[str, Any]) -> None:
        async with self._lock:
            self.file_path.write_text(json.dumps(data, indent=2))

    async def add_feedback(self, entry: FeedbackEntry) -> None:
        data = await self._read()
        data.setdefault("feedback", []).append(entry.as_dict())
        stats = data.setdefault("stats", {})
        stats["total_messages"] = stats.get("total_messages", 0) + 1
        user_counts = stats.setdefault("user_message_counts", {})
        user_counts[str(entry.user_id)] = user_counts.get(str(entry.user_id), 0) + 1
        await self._write(data)

    async def get_stats(self) -> Tuple[int, List[Tuple[str, int]]]:
        data = await self._read()
        stats = data.get("stats", {})
        total = stats.get("total_messages", 0)
        user_counts = stats.get("user_message_counts", {})
        top_users = sorted(user_counts.items(), key=lambda item: item[1], reverse=True)
        return total, top_users

    async def export_csv(self) -> BytesIO:
        data = await self._read()
        feedback = data.get("feedback", [])
        if not feedback:
            raise ValueError("No feedback to export.")

        string_buffer = StringIO()
        writer = csv.DictWriter(
            string_buffer,
            fieldnames=["timestamp", "user_id", "username", "full_name", "text"],
        )
        writer.writeheader()
        for item in feedback:
            writer.writerow(item)

        byte_buffer = BytesIO(string_buffer.getvalue().encode("utf-8"))
        byte_buffer.name = "feedback_export.csv"
        return byte_buffer

    async def clear(self) -> None:
        await self._write(
            {
                "feedback": [],
                "stats": {
                    "total_messages": 0,
                    "user_message_counts": {},
                },
            }
        )


class EmployeeDirectory:
    """Loads employee data from a CSV file and allows simple lookups."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._lock = asyncio.Lock()
        self._employees: List[Employee] = []

    async def ensure_loaded(self) -> None:
        await self.reload()

    async def reload(self) -> None:
        async with self._lock:
            try:
                employees = await asyncio.to_thread(self._read_csv)
            except FileNotFoundError:
                logging.error("Employee data file not found: %s", self.file_path)
                self._employees = []
                return
            except Exception as exc:
                logging.exception("Failed to read employee data: %s", exc)
                raise

            self._employees = employees

    def _read_csv(self) -> List[Employee]:
        employees: List[Employee] = []
        with self.file_path.open(encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            required = {"name", "department", "role", "email"}
            if reader.fieldnames is None or required - set(reader.fieldnames):
                missing = ", ".join(sorted(required - set(reader.fieldnames or [])))
                raise ValueError(
                    f"Employee CSV missing required columns: {missing or 'недоступно'}"
                )

            for row in reader:
                name = (row.get("name") or "").strip()
                department = (row.get("department") or "").strip()
                role = (row.get("role") or "").strip()
                email = (row.get("email") or "").strip()
                if not name or not email:
                    logging.warning("Skipping employee row due to missing name/email: %s", row)
                    continue
                employees.append(Employee(name=name, department=department, role=role, email=email))
        return employees

    async def summarize(self) -> Tuple[int, Dict[str, int]]:
        await self.ensure_loaded()
        async with self._lock:
            total = len(self._employees)
            per_department: Dict[str, int] = {}
            for entry in self._employees:
                key = entry.department or "Не указан"
                per_department[key] = per_department.get(key, 0) + 1
            return total, dict(sorted(per_department.items(), key=lambda item: item[0]))

    async def search(self, query: str, limit: int = 10) -> List[Employee]:
        await self.ensure_loaded()
        query_lower = query.lower()
        async with self._lock:
            return [
                employee
                for employee in self._employees
                if query_lower in employee.name.lower() or query_lower in employee.role.lower()
            ][:limit]

    async def by_department(self, department: str, limit: int = 20) -> List[Employee]:
        await self.ensure_loaded()
        department_lower = department.lower()
        async with self._lock:
            return [
                employee
                for employee in self._employees
                if department_lower in employee.department.lower()
            ][:limit]

    async def find_email(self, name_query: str) -> List[Employee]:
        await self.ensure_loaded()
        query_lower = name_query.lower()
        async with self._lock:
            return [employee for employee in self._employees if query_lower in employee.name.lower()]


def load_config() -> Tuple[str, int]:
    """Load required configuration from environment variables."""

    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN")
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")

    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set in the environment.")
    if not admin_chat_id:
        raise RuntimeError("ADMIN_CHAT_ID is not set in the environment.")

    try:
        admin_chat_id_int = int(admin_chat_id)
    except ValueError as exc:
        raise RuntimeError("ADMIN_CHAT_ID must be an integer.") from exc

    return bot_token, admin_chat_id_int


def format_stats(total: int, top_users: List[Tuple[str, int]]) -> str:
    """Format statistics for display in the chat."""

    lines = [f"Всего сообщений: {total}"]
    if top_users:
        lines.append("Топ пользователей:")
        for index, (user_id, count) in enumerate(top_users[:5], start=1):
            lines.append(f"{index}. {user_id}: {count}")
    else:
        lines.append("Нет данных о пользователях.")
    return "\n".join(lines)


def is_admin(user_id: int, admin_chat_id: int) -> bool:
    return user_id == admin_chat_id


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я бот для сбора обратной связи.\n"
        "Вот что я умею:\n"
        "/feedback <текст> — отправить сообщение сразу.\n"
        "/feedback — я попрошу ввести текст.\n"
        "/stats — показать статистику.\n"
        "/export — экспортировать данные (для администратора).\n"
        "/clear — очистить базу (для администратора).\n"
        "/employees — показать сводку по сотрудникам.\n"
        "/find_employee <запрос> — найти сотрудника по имени или роли.\n"
        "/department <название> — сотрудники отдела.\n"
        "/employee_email <имя> — узнать email сотрудника."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Доступные команды:\n"
        "/start — приветствие.\n"
        "/help — помощь.\n"
        "/feedback <текст> — отправить обратную связь.\n"
        "/feedback — отправить обратную связь через диалог.\n"
        "/cancel — отменить диалог обратной связи.\n"
        "/stats — статистика по сообщениям.\n"
        "/export — экспорт CSV (только администратор).\n"
        "/clear — очистка базы (только администратор).\n"
        "/employees — краткая сводка по сотрудникам.\n"
        "/find_employee <запрос> — поиск по имени или роли.\n"
        "/department <название> — сотрудники выбранного отдела.\n"
        "/employee_email <имя> — email сотрудника."
    )


async def handle_feedback_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    storage: FeedbackStorage,
    admin_chat_id: int,
) -> int | None:
    message = update.message
    if message is None:
        return ConversationHandler.END

    if context.args:
        feedback_text = " ".join(context.args).strip()
        if feedback_text:
            await save_feedback_and_notify(
                context, message, feedback_text, storage, admin_chat_id
            )
            await message.reply_text("Спасибо за обратную связь!")
            return ConversationHandler.END

    await message.reply_text("Пожалуйста, отправьте текст вашей обратной связи.")
    return AWAITING_FEEDBACK_TEXT


async def handle_feedback_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    storage: FeedbackStorage,
    admin_chat_id: int,
) -> int:
    message = update.message
    if message is None or not message.text:
        await message.reply_text("Не удалось получить текст. Попробуйте ещё раз.")
        return AWAITING_FEEDBACK_TEXT

    feedback_text = message.text.strip()
    if not feedback_text:
        await message.reply_text("Текст не может быть пустым. Попробуйте ещё раз.")
        return AWAITING_FEEDBACK_TEXT

    await save_feedback_and_notify(
        context, message, feedback_text, storage, admin_chat_id
    )
    await message.reply_text("Спасибо! Ваше сообщение сохранено.")
    return ConversationHandler.END


async def save_feedback_and_notify(
    context: ContextTypes.DEFAULT_TYPE,
    message: Message,
    feedback_text: str,
    storage: FeedbackStorage,
    admin_chat_id: int,
) -> None:
    user = message.from_user
    entry = FeedbackEntry(
        user_id=user.id if user else 0,
        username=user.username if user else None,
        full_name=user.full_name if user else None,
        text=feedback_text,
    )

    await storage.add_feedback(entry)

    try:
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text=(
                "📬 Новая обратная связь\n"
                f"Пользователь: {entry.full_name or entry.username or entry.user_id}\n"
                f"ID: {entry.user_id}\n"
                f"Текст: {entry.text}"
            ),
        )
    except Exception as exc:  # broad so the user is not blocked
        logging.error("Failed to notify admin: %s", exc)


async def stats_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, storage: FeedbackStorage
) -> None:
    message = update.message
    if message is None:
        return

    total, top_users = await storage.get_stats()
    formatted = format_stats(total, top_users)
    await message.reply_text(formatted)


async def export_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    storage: FeedbackStorage,
    admin_chat_id: int,
) -> None:
    message = update.message
    if message is None:
        return

    user = message.from_user
    if user is None or not is_admin(user.id, admin_chat_id):
        await message.reply_text("Команда доступна только администратору.")
        return

    try:
        csv_buffer = await storage.export_csv()
    except ValueError as exc:
        await message.reply_text(str(exc))
        return
    except Exception as exc:
        logging.exception("Unexpected error during export.")
        await message.reply_text("Не удалось подготовить экспорт. Попробуйте позже.")
        return

    await message.reply_document(document=csv_buffer, filename="feedback_export.csv")


async def clear_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    storage: FeedbackStorage,
    admin_chat_id: int,
) -> None:
    message = update.message
    if message is None:
        return

    user = message.from_user
    if user is None or not is_admin(user.id, admin_chat_id):
        await message.reply_text("Команда доступна только администратору.")
        return

    await storage.clear()
    await message.reply_text("База очищена.")


async def cancel_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    if message:
        await message.reply_text("Отмена операции.")
    return ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error("Exception while handling an update: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Произошла ошибка. Попробуйте ещё раз позже."
            )
        except Exception:  # ensure no error loops
            logging.debug("Failed to send error message to user.")


async def employees_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    directory: EmployeeDirectory,
) -> None:
    message = update.message
    if message is None:
        return

    try:
        total, per_department = await directory.summarize()
    except ValueError as exc:
        await message.reply_text(
            "Файл с сотрудниками содержит ошибки: " + str(exc)
        )
        return
    except FileNotFoundError:
        await message.reply_text("Файл сотрудников не найден.")
        return
    except Exception as exc:
        logging.exception("Failed to summarize employees.")
        await message.reply_text("Не удалось загрузить данные сотрудников.")
        return

    if total == 0:
        await message.reply_text("Список сотрудников пуст или недоступен.")
        return

    lines = [f"Всего сотрудников: {total}", "По отделам:"]
    for department, count in per_department.items():
        lines.append(f"• {department}: {count}")
    lines.append("\nИспользуйте /find_employee, /department или /employee_email для подробностей.")

    await message.reply_text("\n".join(lines))


async def find_employee_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    directory: EmployeeDirectory,
) -> None:
    message = update.message
    if message is None:
        return

    if context.args:
        query = " ".join(context.args).strip()
    else:
        await message.reply_text("Укажите имя или роль сотрудника после команды, например /find_employee Иван.")
        return

    if not query:
        await message.reply_text("Запрос не может быть пустым.")
        return

    try:
        results = await directory.search(query)
    except Exception:
        logging.exception("Failed to search employee data.")
        await message.reply_text("Не удалось выполнить поиск. Попробуйте позже.")
        return

    if not results:
        await message.reply_text("Сотрудники не найдены.")
        return

    response = ["Найдено сотрудников:"]
    for employee in results:
        response.append(employee.formatted())
        response.append("")

    await message.reply_text("\n".join(response).strip())


async def department_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    directory: EmployeeDirectory,
) -> None:
    message = update.message
    if message is None:
        return

    if context.args:
        department = " ".join(context.args).strip()
    else:
        await message.reply_text(
            "Укажите название отдела после команды, например /department IT."
        )
        return

    if not department:
        await message.reply_text("Название отдела не может быть пустым.")
        return

    try:
        results = await directory.by_department(department)
    except Exception:
        logging.exception("Failed to load department data.")
        await message.reply_text("Не удалось получить данные отдела.")
        return

    if not results:
        await message.reply_text("В этом отделе сотрудников не найдено.")
        return

    response = [f"Сотрудники отдела '{department}':"]
    for employee in results:
        response.append(employee.formatted())
        response.append("")

    await message.reply_text("\n".join(response).strip())


async def employee_email_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    directory: EmployeeDirectory,
) -> None:
    message = update.message
    if message is None:
        return

    if context.args:
        query = " ".join(context.args).strip()
    else:
        await message.reply_text(
            "Укажите имя сотрудника после команды, например /employee_email Мария."
        )
        return

    if not query:
        await message.reply_text("Имя сотрудника не может быть пустым.")
        return

    try:
        matches = await directory.find_email(query)
    except Exception:
        logging.exception("Failed to search emails.")
        await message.reply_text("Не удалось получить email. Попробуйте позже.")
        return

    if not matches:
        await message.reply_text("Сотрудники с таким именем не найдены.")
        return

    response = ["Email сотрудников:"]
    for employee in matches:
        response.append(f"{employee.name}: {employee.email}")

    await message.reply_text("\n".join(response))


def build_application(
    token: str,
    storage: FeedbackStorage,
    admin_chat_id: int,
    directory: EmployeeDirectory,
) -> Application:
    application = (
        ApplicationBuilder()
        .token(token)
        .rate_limiter(AIORateLimiter())
        .build()
    )

    feedback_handler = ConversationHandler(
        entry_points=[
            CommandHandler(
                "feedback",
                lambda update, context: handle_feedback_command(
                    update, context, storage, admin_chat_id
                ),
            )
        ],
        states={
            AWAITING_FEEDBACK_TEXT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    lambda update, context: handle_feedback_response(
                        update, context, storage, admin_chat_id
                    ),
                )
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_feedback)],
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(feedback_handler)
    application.add_handler(
        CommandHandler(
            "stats", lambda update, context: stats_command(update, context, storage)
        )
    )
    application.add_handler(
        CommandHandler(
            "export",
            lambda update, context: export_command(update, context, storage, admin_chat_id),
        )
    )
    application.add_handler(
        CommandHandler(
            "clear",
            lambda update, context: clear_command(update, context, storage, admin_chat_id),
        )
    )
    application.add_handler(
        CommandHandler(
            "employees",
            lambda update, context: employees_command(update, context, directory),
        )
    )
    application.add_handler(
        CommandHandler(
            "find_employee",
            lambda update, context: find_employee_command(update, context, directory),
        )
    )
    application.add_handler(
        CommandHandler(
            "department",
            lambda update, context: department_command(update, context, directory),
        )
    )
    application.add_handler(
        CommandHandler(
            "employee_email",
            lambda update, context: employee_email_command(update, context, directory),
        )
    )

    application.add_error_handler(error_handler)

    return application


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    try:
        bot_token, admin_chat_id = load_config()
    except RuntimeError as exc:
        logging.error(exc)
        raise SystemExit(1) from exc

    storage = FeedbackStorage(Path("feedback.json"))
    directory = EmployeeDirectory(Path("employees.csv"))
    application = build_application(bot_token, storage, admin_chat_id, directory)

    logging.info("Starting bot...")
    application.run_polling(close_loop=False)


if __name__ == "__main__":
    main()

