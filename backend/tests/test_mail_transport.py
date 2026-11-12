import os
import unittest
from unittest.mock import MagicMock,patch
from src.parcers import mailer

class MailTransportTests(unittest.TestCase):
    def config(self,**values):
        return patch.dict(os.environ,{"MULTIMARKET_SMTP_HOST":"smtp.example.test","MULTIMARKET_SMTP_FROM":"MultiMarket <mail@example.test>",**values},clear=True)
    def test_starttls_is_used_before_login_and_send(self):
        with self.config(MULTIMARKET_SMTP_USERNAME="sender",MULTIMARKET_SMTP_PASSWORD="test-application-password"),patch("smtplib.SMTP") as ctor:
            client=ctor.return_value.__enter__.return_value
            mailer.send("recipient@example.test","Subject","Plain message")
            self.assertEqual([c[0] for c in client.method_calls],["starttls","login","send_message"])
            self.assertEqual(ctor.call_args.args,("smtp.example.test",587))
    def test_ssl_uses_verified_context_and_standard_port(self):
        with self.config(MULTIMARKET_SMTP_SECURITY="ssl"),patch("smtplib.SMTP_SSL") as ctor:
            mailer.send("recipient@example.test","Subject","Plain message")
            self.assertEqual(ctor.call_args.args,("smtp.example.test",465));self.assertIn("context",ctor.call_args.kwargs)
    def test_plain_smtp_is_only_available_for_local_test_servers(self):
        with self.config(MULTIMARKET_SMTP_SECURITY="none"):self.assertIsNone(mailer.settings())
        with self.config(MULTIMARKET_SMTP_HOST="127.0.0.1",MULTIMARKET_SMTP_SECURITY="none"):self.assertIsNotNone(mailer.settings())
    def test_invalid_mail_configuration_is_not_reported_ready(self):
        for extra in [{"MULTIMARKET_SMTP_PORT":"-1"},{"MULTIMARKET_SMTP_PORT":"x"},{"MULTIMARKET_SMTP_FROM":"bad\r\nBcc: b@example.test"}]:
            with self.config(**extra):self.assertIsNone(mailer.settings())
    def test_public_url_rejects_credentials_and_invalid_origins(self):
        for url in ["javascript:alert(1)","https:","https://user:pw@example.test","https://example.test/path","https://example.test:bad","http://external.example.test"]:
            with patch.dict(os.environ,{"MULTIMARKET_PUBLIC_URL":url}):
                with self.assertRaises(RuntimeError):mailer.public_url()
    def test_smtp_failures_are_generic_and_do_not_expose_password(self):
        with self.config(MULTIMARKET_SMTP_PASSWORD="private-test-value"),patch("smtplib.SMTP",side_effect=OSError("internal connection details")):
            with self.assertRaisesRegex(RuntimeError,"Не удалось отправить письмо") as caught:mailer.send("recipient@example.test","Subject","Plain message")
            self.assertNotIn("private-test-value",str(caught.exception));self.assertNotIn("internal",str(caught.exception))
