from django.test import TestCase
from app.bot.dialog import process_input
from app.core.models import BotDialog, CategoryGroup, CategoryItem, Ticket
from app.bot.telegram import consume_update, send_reply, send_text
from app.bot.dialog import Reply
from aiogram.types import Update
from asgiref.sync import async_to_sync
from html import unescape
import re


class BotTests(TestCase):
    def say(self, text, user=123):
        return process_input(user, "Ирина", text)

    def draft(self):
        self.say("/start")
        self.say("Подать заявку")
        self.say("Оборудование")
        self.say("Проектор")
        self.say("Не включается")
        return self.say("@irina")

    def test_full_dialog_persistence_and_duplicate_confirmation(self):
        self.assertIn("обслуживан", self.say("/start").text)
        confirmation = self.draft()
        self.assertIn("Не включается", confirmation.text)
        self.assertEqual(BotDialog.objects.get(telegram_id=123).step, "confirm")
        self.assertIn("З-000001", self.say("Подтвердить").text)
        self.say("Подтвердить")
        self.assertEqual(Ticket.objects.count(), 1)
        ticket = Ticket.objects.get()
        self.assertEqual(ticket.contact, "@irina")
        self.assertEqual(ticket.history.count(), 1)
        Ticket.objects.filter(pk=ticket.pk).update(status=Ticket.Status.WORK)
        self.assertIn("В работе", self.say("Подтвердить").text)

    def test_blank_nontext_back_and_invalid_categories(self):
        self.say("Подать заявку")
        for text in [None, "", "   ", "Несуществующая"]:
            self.say(text)
            self.assertEqual(BotDialog.objects.get().step, "group")
        self.say("Назад")
        self.assertEqual(BotDialog.objects.get().step, "idle")
        self.draft()
        expected = ["contact", "description", "item", "group", "idle"]
        for step in expected:
            self.say("Назад")
            self.assertEqual(BotDialog.objects.get().step, step)
        self.say("Подать заявку")
        self.say("Оборудование")
        CategoryItem.objects.filter(name="Проектор").update(active=False)
        self.say("Проектор")
        self.assertEqual(BotDialog.objects.get().step, "item")
        CategoryGroup.objects.filter(name="Оборудование").update(active=False)
        self.say("Принтер")
        self.assertEqual(BotDialog.objects.get().step, "group")

    def test_status_button_pages_own_tickets_and_numbers_stay_unique(self):
        from app.bot.presentation import keyboard
        for _ in range(6):
            self.draft()
            self.say("Подтвердить")
        numbers = {ticket.number for ticket in Ticket.objects.all()}
        keys = {ticket.key for ticket in Ticket.objects.all()}
        self.assertEqual(len(numbers), 6)
        self.assertEqual(len(keys), 6)
        reply = self.say("Узнать статус")
        self.assertIn("Страница 1 из 2", reply.text)
        buttons = [button for row in keyboard(reply).inline_keyboard for button in row]
        self.assertEqual(sum(button.callback_data.startswith("open:") for button in buttons), 5)
        page = process_input(123, "Ирина", None, callback=next(button.callback_data for button in buttons if button.callback_data.startswith("pg:")))
        self.assertIn("Страница 2 из 2", page.text)
        opened = process_input(123, "Ирина", None, callback=next(
            button.callback_data for row in keyboard(page).inline_keyboard for button in row
            if button.callback_data.startswith("open:")))
        self.assertIn("Описание:", opened.text)
        self.assertIn("История:", opened.text)
        self.assertIn("пока нет заявок", self.say("Узнать статус", user=456).text.lower())

    def test_status_preserves_draft_and_hides_other_owner(self):
        self.draft()
        ticket_reply = self.say("Подтвердить")
        number = Ticket.objects.get().number
        self.say("Подать заявку")
        self.say("Оборудование")
        self.assertIn("Новая", self.say(f"/status {number}").text)
        self.assertEqual(BotDialog.objects.get(telegram_id=123).step, "item")
        self.assertIn("не найдена", self.say(f"/status {number}", user=456).text)
        self.assertNotIn("@irina", self.say(f"/status {number}", user=456).text)

    def test_validation_and_deactivation_before_confirmation(self):
        self.draft()
        self.say("Назад")
        for invalid in [None, "   ", "x" * 301]:
            self.say(invalid)
            self.assertEqual(BotDialog.objects.get().step, "contact")
        self.say("@irina")
        CategoryItem.objects.filter(name="Проектор").update(active=False)
        self.say("Подтвердить")
        self.assertEqual(Ticket.objects.count(), 0)
        self.assertEqual(BotDialog.objects.get().step, "group")

    def test_private_only_and_duplicate_update_does_not_advance_dialog(self):
        def update(update_id, chat_type, text):
            return Update.model_validate({"update_id": update_id, "message": {
                "message_id": update_id, "date": 1000,
                "chat": {"id": 123, "type": chat_type},
                "from": {"id": 123, "is_bot": False, "first_name": "Ирина"}, "text": text}})
        self.assertIsNone(consume_update(update(1, "group", "Подать заявку")))
        self.assertFalse(BotDialog.objects.exists())
        consume_update(update(2, "private", "Подать заявку"))
        consume_update(update(3, "private", "Оборудование"))
        consume_update(update(4, "private", "Проектор"))
        consume_update(update(5, "private", "Нет изображения"))
        self.assertIsNone(consume_update(update(5, "private", "Нет изображения")))
        self.assertEqual(BotDialog.objects.get().step, "contact")

    def test_long_confirmation_fits_telegram_messages(self):
        calls = []
        class Transport:
            async def send_message(self, chat_id, text, **kwargs):
                calls.append((text, kwargs))
        self.say("Подать заявку")
        self.say("Оборудование")
        self.say("Проектор")
        self.say("д" * 4000)
        reply = self.say("к" * 300)
        value = reply.text
        self.assertGreater(len(value), 4096)
        async_to_sync(send_reply)(Transport(), 123, reply)
        decoded = [unescape(re.sub(r'<[^>]+>', '', text)) for text, kwargs in calls]
        self.assertIn("д" * 4000, "".join(decoded))
        self.assertIn("к" * 300, "".join(decoded))
        self.assertTrue(all(len(text.encode('utf-16-le')) // 2 <= 4096 for text in decoded))
        self.assertIsNotNone(calls[-1][1]["reply_markup"])
        self.assertIsNone(calls[0][1]["reply_markup"])

    def test_partial_message_failure_is_reported_and_retry_sends_all_parts(self):
        calls = []
        class Transport:
            failed = False
            attempts = 0
            async def send_message(self, chat_id, text, **kwargs):
                self.attempts += 1
                if self.attempts == 2 and not self.failed:
                    self.failed = True
                    raise TimeoutError("Недоступно")
                calls.append(text)
        transport = Transport()
        value = "а" * 4000 + "б"
        with self.assertRaises(TimeoutError):
            async_to_sync(send_text)(transport, 123, value)
        async_to_sync(send_text)(transport, 123, value)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual("".join(calls[1:]), value)
