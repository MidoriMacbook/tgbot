from html.parser import HTMLParser
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import Update
from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings

from app.bot.dialog import process_input
from app.bot.telegram import consume_update, markup, send_reply, send_text
from app.core.models import BotDialog, CategoryGroup, CategoryItem, Ticket


class ParsedHTML(HTMLParser):
    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.text = []
        self.feed(value)
        self.close()
        if self.stack:
            raise AssertionError(f'Незакрытые теги: {self.stack}')

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise AssertionError(f'Нарушена вложенность: {tag}')

    def handle_data(self, data):
        self.text.append(data)


def visible(value):
    return ''.join(ParsedHTML(value).text)


@override_settings(TELEGRAM_CUSTOM_EMOJI=True)
class BotPresentationTests(TestCase):
    def say(self, text, user=123):
        return process_input(user, 'Заявитель', text)

    def confirmation(self, description='Не работает <проектор> & питание', contact='@user'):
        for value in ['Подать заявку', 'Оборудование', 'Проектор', description, contact]:
            reply = self.say(value)
        return reply

    def callback(self, update_id, data, user=123):
        update = Update.model_validate({'update_id': update_id, 'callback_query': {
            'id': f'query-{update_id}', 'chat_instance': 'test', 'data': data,
            'from': {'id': user, 'is_bot': False, 'first_name': 'Заявитель'},
            'message': {'message_id': 1, 'date': 1000, 'chat': {'id': user, 'type': 'private'}}}})
        return consume_update(update)

    def test_menu_has_inline_reference_icons_and_semantic_colors(self):
        keyboard = markup(self.say('/start'))
        create = keyboard.inline_keyboard[0][0]
        self.assertEqual(create.text, 'Подать заявку')
        self.assertEqual(create.callback_data, 'new')
        self.assertEqual(create.style, 'primary')
        self.assertEqual(create.icon_custom_emoji_id, '5256263173928926820')
        status = keyboard.inline_keyboard[1][0]
        self.assertIsNone(status.style)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertNotIn('Открыть панель', labels)
        confirm = markup(self.confirmation()).inline_keyboard[0][0]
        self.assertEqual(confirm.style, 'success')

    def test_confirmation_is_html_and_user_content_is_escaped(self):
        reply = self.confirmation(contact='<b>мой контакт</b> & "кабинет"')
        bot = type('Transport', (), {'send_message': AsyncMock()})()
        async_to_sync(send_reply)(bot, 123, reply)
        body = ''.join(call.args[1] for call in bot.send_message.call_args_list)
        self.assertTrue(all(call.kwargs['parse_mode'] == 'HTML' for call in bot.send_message.call_args_list))
        self.assertIn('<tg-emoji', body)
        self.assertIn('<blockquote>', body)
        self.assertIn('&lt;b&gt;мой контакт&lt;/b&gt;', body)
        self.assertIn('<b>мой контакт</b>', visible(body))
        self.assertIn('Не работает <проектор> & питание', visible(body))

    def test_long_unicode_messages_preserve_content_and_balanced_html(self):
        description = '😀' * 4000
        contact = '<' * 300
        reply = self.confirmation(description, contact)
        bot = type('Transport', (), {'send_message': AsyncMock()})()
        async_to_sync(send_reply)(bot, 123, reply)
        calls = bot.send_message.call_args_list
        decoded = [visible(call.args[1]) for call in calls]
        self.assertGreater(len(calls), 1)
        self.assertTrue(all(len(value.encode('utf-16-le')) // 2 <= 4096 for value in decoded))
        self.assertIn(description, ''.join(decoded))
        self.assertIn(contact, ''.join(decoded))
        self.assertIsNotNone(calls[-1].kwargs['reply_markup'])
        self.assertTrue(all(call.kwargs['reply_markup'] is None for call in calls[:-1]))

    def test_inline_selection_uses_ids_even_for_reserved_category_names(self):
        group = CategoryGroup.objects.get(name='Оборудование')
        group.name = 'Назад'
        group.save()
        item = CategoryItem.objects.get(name='Проектор')
        item.name = 'Подать заявку'
        item.save()
        result = self.callback(1, 'new')
        self.assertIsNotNone(result)
        reply = result[1]
        button = next(row[0] for row in markup(reply).inline_keyboard if row[0].text == 'Назад')
        result = self.callback(2, button.callback_data)
        self.assertEqual(BotDialog.objects.get().step, 'item')
        button = next(row[0] for row in markup(result[1]).inline_keyboard if row[0].text == 'Подать заявку')
        self.callback(3, button.callback_data)
        self.assertEqual(BotDialog.objects.get().step, 'description')

    def test_old_or_foreign_buttons_do_not_change_another_draft(self):
        old = markup(self.say('Подать заявку')).inline_keyboard[0][0].callback_data
        self.say('Подать заявку')
        self.callback(10, old)
        self.assertEqual(BotDialog.objects.get(telegram_id=123).step, 'group')
        self.say('Подать заявку', user=456)
        self.callback(11, old, user=456)
        self.assertEqual(BotDialog.objects.get(telegram_id=456).step, 'group')

    def test_confirmation_callback_is_idempotent(self):
        button = markup(self.confirmation()).inline_keyboard[0][0]
        self.callback(20, button.callback_data)
        self.callback(21, button.callback_data)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(BotDialog.objects.get().step, 'submitted')

    def test_confirmation_is_bound_to_the_displayed_contact(self):
        old = markup(self.confirmation(contact='old-contact')).inline_keyboard[0][0].callback_data
        self.say('Назад')
        current = markup(self.say('new-contact')).inline_keyboard[0][0].callback_data
        self.assertNotEqual(old, current)
        self.callback(30, old)
        self.assertFalse(Ticket.objects.exists())
        self.callback(31, current)
        self.assertEqual(Ticket.objects.get().contact, 'new-contact')

    def test_unavailable_premium_retries_without_losing_button_actions(self):
        error = TelegramBadRequest(method=SendMessage(chat_id=123, text='test'), message='CUSTOM_EMOJI_INVALID')
        bot = type('Transport', (), {'send_message': AsyncMock(side_effect=[error, error, None])})()
        async_to_sync(send_reply)(bot, 123, self.say('/start'))
        calls = bot.send_message.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertIn('<tg-emoji', calls[1].args[1])
        self.assertNotIn('<tg-emoji', calls[-1].args[1])
        button = calls[-1].kwargs['reply_markup'].inline_keyboard[0][0]
        self.assertEqual(button.callback_data, 'new')
        self.assertEqual(button.style, 'primary')
        self.assertIsNone(button.icon_custom_emoji_id)

    def test_unrelated_telegram_errors_are_not_hidden(self):
        error = TelegramBadRequest(method=SendMessage(chat_id=123, text='test'), message='chat not found')
        bot = type('Transport', (), {'send_message': AsyncMock(side_effect=error)})()
        with self.assertRaises(TelegramBadRequest):
            async_to_sync(send_reply)(bot, 123, self.say('/start'))
        self.assertEqual(bot.send_message.call_count, 1)

    @override_settings(TELEGRAM_CUSTOM_EMOJI=False)
    def test_disabled_premium_keeps_html_and_colored_buttons(self):
        bot = type('Transport', (), {'send_message': AsyncMock()})()
        async_to_sync(send_reply)(bot, 123, self.say('/start'))
        call = bot.send_message.call_args
        self.assertNotIn('<tg-emoji', call.args[1])
        self.assertIn('<b>', call.args[1])
        button = call.kwargs['reply_markup'].inline_keyboard[0][0]
        self.assertEqual(button.style, 'primary')
        self.assertIsNone(button.icon_custom_emoji_id)

    def test_old_plain_notifications_are_escaped_at_transport_boundary(self):
        text = 'Заявка З-000001: Выполнена.\nИсправлено <питание> & сеть'
        bot = type('Transport', (), {'send_message': AsyncMock()})()
        async_to_sync(send_text)(bot, 123, text)
        call = bot.send_message.call_args
        self.assertEqual(call.kwargs['parse_mode'], 'HTML')
        self.assertIn('&lt;питание&gt; &amp; сеть', call.args[1])
        self.assertIn('З-000001', visible(call.args[1]))

    def test_callback_response_edits_message_instead_of_sending(self):
        bot = type('Transport', (), {'send_message': AsyncMock(), 'edit_message_text': AsyncMock()})()
        async_to_sync(send_reply)(bot, 123, self.say('Подать заявку'), message_id=45)
        bot.send_message.assert_not_called()
        self.assertEqual(bot.edit_message_text.call_count, 1)
        self.assertEqual(bot.edit_message_text.call_args.kwargs['message_id'], 45)
        self.assertIsNotNone(bot.edit_message_text.call_args.kwargs['reply_markup'])

    def test_unchanged_message_does_not_send_a_duplicate(self):
        error = TelegramBadRequest(method=SendMessage(chat_id=123, text='test'), message='message is not modified')
        bot = type('Transport', (), {'send_message': AsyncMock(), 'edit_message_text': AsyncMock(side_effect=error)})()
        async_to_sync(send_reply)(bot, 123, self.say('/start'), message_id=45)
        bot.send_message.assert_not_called()

    def test_missing_edit_target_falls_back_to_new_message(self):
        error = TelegramBadRequest(method=SendMessage(chat_id=123, text='test'), message='message to edit not found')
        bot = type('Transport', (), {'send_message': AsyncMock(), 'edit_message_text': AsyncMock(side_effect=error)})()
        async_to_sync(send_reply)(bot, 123, self.say('/start'), message_id=45)
        self.assertEqual(bot.send_message.call_count, 1)

    def test_lower_keyboard_is_colored_and_fallback_labels_keep_working(self):
        from app.bot.presentation import lower_keyboard, without_button_icons
        keyboard = lower_keyboard()
        self.assertEqual([row[0].style for row in keyboard.keyboard], ['primary', None, 'danger'])
        self.assertTrue(all('панель' not in row[0].text.lower() for row in keyboard.keyboard))
        plain = without_button_icons(keyboard)
        self.say(plain.keyboard[0][0].text)
        self.assertEqual(BotDialog.objects.get().step, 'group')

    def test_commands_open_a_new_message_and_the_form_keeps_one_screen(self):
        from app.bot.telegram import edit_target
        text_update = type('Update', (), {'callback_query': None, 'message': type('Message', (), {'text': 'Подать заявку'})()})()
        self.assertEqual(edit_target(text_update, 45), (45, False, True))
        description = type('Update', (), {'callback_query': None, 'message': type('Message', (), {'text': 'Не печатает'})()})()
        self.assertEqual(edit_target(description, 45, 'description'), (45, False, True))
        start = type('Update', (), {'callback_query': None, 'message': type('Message', (), {'text': '/start'})()})()
        self.assertEqual(edit_target(start, None), (None, True, True))
        self.assertEqual(edit_target(start, 45, 'description'), (None, True, True))
        status = type('Update', (), {'callback_query': None, 'message': type('Message', (), {'text': '/status З-000001'})()})()
        self.assertEqual(edit_target(status, 45, 'description'), (None, False, False))
        query = type('Query', (), {'message': type('Message', (), {'message_id': 7})()})()
        callback = type('Update', (), {'callback_query': query, 'message': None})()
        self.assertEqual(edit_target(callback, 1), (7, False, True))
