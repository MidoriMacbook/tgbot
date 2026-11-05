import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from app import config
import run


class HostingConfigurationTests(SimpleTestCase):
    def test_dotenv_has_no_execution_and_preserves_container_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, '.env').write_text('PORT=9999\nEXAMPLE=${PORT}\nVALUE=$(whoami)\n', encoding='utf-8')
            with patch.object(config, 'BASE_DIR', Path(directory)), patch.dict(os.environ, {'PORT': '10064'}, clear=True):
                config.load_environment()
                config.load_environment()
                self.assertEqual(os.environ['PORT'], '10064')
                self.assertEqual(os.environ['EXAMPLE'], '${PORT}')
                self.assertEqual(os.environ['VALUE'], '$(whoami)')

    def test_bad_configuration_errors_do_not_repeat_values(self):
        with patch.dict(os.environ, {'BOT_JSON': 'secret malformed json', 'PORT': 'secret-invalid-port'}):
            for callback in [lambda: config.env_dict('BOT_JSON'), lambda: config.env_number('PORT', 10064, 1, 65535)]:
                with self.assertRaises(ValueError) as caught:
                    callback()
                self.assertNotIn('secret', str(caught.exception))

    @override_settings(BOT_CONFIG={'token': 'safe-test-token'})
    def test_launcher_starts_three_processes_and_stops_siblings_on_any_exit(self):
        setup = [Mock(returncode=0) for _ in range(3)]
        for process in setup:
            process.poll.return_value = 0
        web = Mock(returncode=0)
        web.poll.return_value = 0
        bot, notifications = Mock(), Mock()
        bot.poll.return_value = notifications.poll.return_value = None
        with patch.dict(os.environ, {}, clear=True), patch.object(run, 'load_environment'), \
             patch.object(run.subprocess, 'Popen', side_effect=[*setup, web, bot, notifications]) as popen:
            self.assertEqual(run.main(), 1)
        commands = [call.args[0][2] for call in popen.call_args_list]
        self.assertEqual(commands, ['migrate', 'bootstrap_chief', 'collectstatic', 'serve', 'runbot', 'notify'])
        for call in popen.call_args_list:
            self.assertEqual(call.kwargs['cwd'], config.BASE_DIR)
            self.assertIs(call.kwargs['shell'], False)
            self.assertTrue(Path(call.args[0][1]).is_absolute())
        bot.terminate.assert_called_once()
        notifications.terminate.assert_called_once()

    @override_settings(TELEGRAM_ALLOW_EMBED=False)
    def test_panel_disallows_embedding_by_default(self):
        response = self.client.get('/login/')
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        self.assertEqual(response['Content-Security-Policy'], "frame-ancestors 'none'")

    @override_settings(TELEGRAM_ALLOW_EMBED=True)
    def test_telegram_embedding_has_restricted_ancestors(self):
        response = self.client.get('/login/')
        self.assertNotIn('X-Frame-Options', response)
        self.assertIn('https://web.telegram.org', response['Content-Security-Policy'])
        self.assertNotIn('frame-ancestors *', response['Content-Security-Policy'])
