import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch,Mock,AsyncMock
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from src.parcers.api import app
from src.parcers import accounts,account_security,library,mailer,monitoring,notifications

PRODUCT={"title":"Phone 128 ГБ", "offers":[{"marketplace":"Ozon","title":"Phone 128 ГБ","url":"https://ozon.ru/product/1","price":100,"currency":"RUB","specifications":[{"name":"Цвет","value":"чёрный"}]}]}

class PersonalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.dbpatch=patch.object(monitoring,"DB_PATH",Path(self.temp.name)/"test.sqlite");self.dbpatch.start();self.addCleanup(self.dbpatch.stop)
        monitoring.init_db();accounts.init_db();library.init_db()
        self.mailpatch=patch("src.parcers.mailer.settings",return_value=None);self.mailpatch.start();self.addCleanup(self.mailpatch.stop)
        self.a,self.b=TestClient(app),TestClient(app);self.addCleanup(self.a.close);self.addCleanup(self.b.close)
        self.ua=self.register(self.a,"alice@example.test");self.ub=self.register(self.b,"bob@example.test")
    def csrf(self,client):return {"X-CSRF-Token":client.get("/api/auth/me").json()["csrf_token"]}
    def register(self,client,email):return client.post("/api/auth/register",headers=self.csrf(client),json={"name":"Test","email":email,"password":"old-password"}).json()["user"]
    def monitor(self,**kw):return monitoring.create_monitor(query="Phone",title="Phone",product_url="https://ozon.ru/product/1",marketplace="Ozon",interval_seconds=900,user_id=self.ua["id"],**kw)
    def test_favorites_are_private_and_csrf_protected(self):
        self.assertEqual(self.a.put("/api/favorites",json=PRODUCT).status_code,403)
        data=self.a.put("/api/favorites",json=PRODUCT,headers=self.csrf(self.a)).json()
        self.assertEqual(self.b.get("/api/favorites").json()["favorites"],[])
        self.assertEqual(self.b.delete("/api/favorites/"+data["id"],headers=self.csrf(self.b)).status_code,404)
        self.assertEqual(len(self.a.get("/api/favorites").json()["favorites"]),1)
    def test_favorite_price_update_is_an_upsert(self):
        one=library.save_favorite(self.ua["id"],PRODUCT)
        data=json.loads(json.dumps(PRODUCT));data["offers"][0]["price"]=90
        two=library.save_favorite(self.ua["id"],data)
        self.assertEqual(one["id"],two["id"]);self.assertEqual(len(library.favorites(self.ua["id"])),1)
    def test_favorites_do_not_overwrite_different_options_at_the_same_url(self):
        one=library.save_favorite(self.ua["id"],PRODUCT)
        data=json.loads(json.dumps(PRODUCT));data["offers"][0]["title"]="Phone 256 ГБ"
        two=library.save_favorite(self.ua["id"],data)
        self.assertNotEqual(one["id"],two["id"]);self.assertEqual(len(library.favorites(self.ua["id"])),2)
    def test_enriching_a_saved_sku_does_not_duplicate_the_favorite(self):
        one=library.save_favorite(self.ua["id"],PRODUCT)
        data=json.loads(json.dumps(PRODUCT));data["offers"][0]["specifications"].append({"name":"Комплектация","value":"Телефон, кабель"})
        two=library.save_favorite(self.ua["id"],data)
        self.assertEqual(one["id"],two["id"]);self.assertEqual(len(library.favorites(self.ua["id"])),1)
    def test_favorite_rejects_foreign_urls_and_invalid_prices(self):
        for url in ["https://ozon.ru.evil.test/p","https://u:p@ozon.ru/p","http://ozon.ru/p","https://ozon.ru:444/p"]:
            data=json.loads(json.dumps(PRODUCT));data["offers"][0]["url"]=url
            with self.assertRaises(ValueError):library.snapshot(data)
        for price in [True,float("inf"),-1]:
            data=json.loads(json.dumps(PRODUCT));data["offers"][0]["price"]=price
            with self.assertRaises(ValueError):library.snapshot(data)
    def test_delivery_is_per_account_and_validated(self):
        point={"id":"osm:N:123","marketplace":"Ozon","region_id":213,"address":"Тверская 7","name":"Ozon","lat":55.75,"lon":37.62}
        payload={"region_id":213,"choices":{"213:Ozon":point}}
        self.assertEqual(self.a.put("/api/preferences/delivery",json=payload,headers=self.csrf(self.a)).status_code,200)
        self.assertIsNone(self.b.get("/api/preferences/delivery").json()["delivery"])
        payload["choices"]["213:Ozon"]["lat"]=100
        self.assertEqual(self.a.put("/api/preferences/delivery",json=payload,headers=self.csrf(self.a)).status_code,422)
    def test_favorites_page_requires_login_and_delivery_remains_public(self):
        with TestClient(app) as guest:
            self.assertEqual(guest.get("/favorites",follow_redirects=False).status_code,303)
            self.assertEqual(guest.get("/compare").status_code,200)
            self.assertEqual(guest.get("/delivery").status_code,200)
    def test_tokens_are_hashed_expiring_and_purpose_bound(self):
        token=account_security.issue(self.ua["id"],"verify")
        with accounts._connect() as db:
            row=dict(db.execute("SELECT * FROM account_tokens").fetchone());self.assertEqual(row["token_hash"],hashlib.sha256(token.encode()).hexdigest());self.assertNotIn(token,str(row))
        with self.assertRaises(ValueError):account_security.consume(token,"reset","new-password")
        account_security.consume(token,"verify")
        self.assertTrue(accounts.get_user(self.ua["id"])["email_verified"])
        with self.assertRaises(ValueError):account_security.consume(token,"verify")
        second=account_security.issue(self.ub["id"],"verify")
        with accounts._connect() as db:db.execute("UPDATE account_tokens SET expires_at=0")
        with self.assertRaises(ValueError):account_security.consume(second,"verify")
    def test_two_consumers_cannot_use_same_reset_token(self):
        token=account_security.issue(self.ua["id"],"reset")
        def consume():
            try:account_security.consume(token,"reset","new-password");return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as executor:self.assertEqual(sum(executor.map(lambda _:consume(),range(2))),1)
    def test_reset_invalidates_other_sessions_and_old_password(self):
        other=TestClient(app);self.addCleanup(other.close)
        other.post("/api/auth/login",headers=self.csrf(other),json={"email":"alice@example.test","password":"old-password"})
        token=account_security.issue(self.ua["id"],"reset")
        response=self.a.post("/api/auth/password-reset/confirm",headers=self.csrf(self.a),json={"token":token,"password":"new-password"})
        self.assertEqual(response.status_code,200)
        self.assertFalse(other.get("/api/auth/me").json()["authenticated"])
        self.assertIsNone(accounts.authenticate_user(email="alice@example.test",password="old-password"))
        self.assertIsNotNone(accounts.authenticate_user(email="alice@example.test",password="new-password"))
    def test_reset_request_does_not_reveal_registered_addresses(self):
        with patch("src.parcers.mailer.settings",return_value={"configured":True}),patch("src.parcers.mailer.action_email") as send:
            known=self.a.post("/api/auth/password-reset/request",headers=self.csrf(self.a),json={"email":"alice@example.test"})
            unknown=self.a.post("/api/auth/password-reset/request",headers=self.csrf(self.a),json={"email":"absent@example.test"})
            self.assertEqual(known.json(),unknown.json());self.assertEqual(send.call_count,1)
            token=send.call_args.args[2];self.assertNotIn(token,known.text)
    def test_verifying_token_does_not_verify_the_current_wrong_account(self):
        token=account_security.issue(self.ua["id"],"verify")
        r=self.b.post("/api/auth/email/confirm",headers=self.csrf(self.b),json={"token":token})
        self.assertEqual(r.status_code,200);self.assertTrue(accounts.get_user(self.ua["id"])["email_verified"]);self.assertFalse(accounts.get_user(self.ub["id"])["email_verified"])
    def test_resending_replaces_previous_link_and_has_a_cooldown(self):
        old=account_security.issue(self.ua["id"],"verify")
        with self.assertRaises(ValueError):account_security.issue(self.ua["id"],"verify")
        with accounts._connect() as db:db.execute("UPDATE account_tokens SET created_at=0")
        new=account_security.issue(self.ua["id"],"verify")
        with self.assertRaises(ValueError):account_security.consume(old,"verify")
        account_security.consume(new,"verify")
    def test_oauth_mailbox_change_invalidates_old_verification_links(self):
        profile=dict(provider="yandex",subject="qa-subject",email="old@example.test",name="Test",picture_url=None,admin_emails=set())
        user=accounts.login_user(**profile)
        token=account_security.issue(user["id"],"verify")
        changed=accounts.login_user(**{**profile,"email":"new@example.test"})
        self.assertFalse(changed["email_verified"])
        with self.assertRaises(ValueError):account_security.consume(token,"verify")
        self.assertFalse(accounts.get_user(user["id"])["email_verified"])
    def test_mail_links_use_configured_origin_not_request_host(self):
        with patch.dict(os.environ,{"MULTIMARKET_PUBLIC_URL":"https://shop.example.test"}),patch("src.parcers.mailer.send") as send:
            mailer.action_email(self.ua,"reset","safe-token")
            self.assertIn("https://shop.example.test/reset-password#token=safe-token",send.call_args.args[2])
    def test_unverified_email_cannot_enable_notifications(self):
        r=self.a.patch("/api/notification-settings",headers=self.csrf(self.a),json={"email_enabled":True})
        self.assertEqual(r.status_code,409)
    def test_target_price_crossing_is_not_repeated_each_poll(self):
        monitor=self.monitor(target_price=100,target_currency="RUB")
        for price in [110,95,90,110,99]:monitoring.record_check(monitor["id"],price=price,currency="RUB",status="ok")
        alerts=monitoring.list_alerts(user_id=self.ua["id"])
        self.assertEqual(len(alerts),2);self.assertEqual({a["reason"] for a in alerts},{"target"})
        monitoring.update_monitor(monitor["id"],user_id=self.ua["id"],target_price=100,target_currency="RUB")
        self.assertIsNone(monitoring.record_check(monitor["id"],price=90,currency="RUB",status="ok"))
    def test_initial_target_and_currency_are_handled_without_false_comparison(self):
        monitor=self.monitor(target_price=100,target_currency="RUB")
        self.assertIsNone(monitoring.record_check(monitor["id"],price=10,currency="USD",status="ok"))
        self.assertEqual(monitoring.record_check(monitor["id"],price=90,currency="RUB",status="ok")["reason"],"target")
    def test_custom_percentage_direction_and_private_read_status(self):
        monitor=self.monitor(threshold_percent=5,alert_direction="drop")
        for price in [100,110,100]:monitoring.record_check(monitor["id"],price=price,currency="RUB",status="ok")
        alerts=monitoring.list_alerts(user_id=self.ua["id"]);self.assertEqual(len(alerts),1)
        alert_id=alerts[0]["id"]
        self.assertEqual(self.b.patch(f"/api/alerts/{alert_id}/read",headers=self.csrf(self.b)).status_code,404)
        self.assertEqual(self.a.patch(f"/api/alerts/{alert_id}/read",headers=self.csrf(self.a)).status_code,200)
        self.assertIsNotNone(monitoring.list_alerts(user_id=self.ua["id"])[0]["read_at"])
    def test_channel_without_in_app_does_not_show_in_inbox(self):
        monitor=self.monitor(notify_in_app=False,notify_email=True,target_price=100)
        monitoring.record_check(monitor["id"],price=90,currency="RUB",status="ok")
        self.assertEqual(monitoring.list_alerts(user_id=self.ua["id"]),[])
        with accounts._connect() as db:self.assertEqual(db.execute("SELECT channel FROM notification_deliveries").fetchone()[0],"email")
    def test_invalid_price_does_not_generate_a_snapshot_or_alert(self):
        monitor=self.monitor(target_price=100)
        for price in [float("nan"),float("inf"),-1]:self.assertIsNone(monitoring.record_check(monitor["id"],price=price,currency="RUB",status="ok"))
        self.assertEqual(monitoring.price_history(monitor["id"]),[])
    def test_new_private_endpoints_require_authentication(self):
        with TestClient(app) as guest:
            for path in ["/api/favorites","/api/preferences/delivery","/api/notification-settings"]:self.assertEqual(guest.get(path).status_code,401)
    def test_another_user_cannot_change_monitor_rule(self):
        monitor=self.monitor()
        self.assertEqual(self.b.patch("/api/monitors/"+monitor["id"],headers=self.csrf(self.b),json={"target_price":1}).status_code,404)
        self.assertIsNone(monitoring.get_monitor(monitor["id"])["target_price"])


class TelegramTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);p=patch.object(monitoring,"DB_PATH",Path(self.temp.name)/"test.sqlite");p.start();self.addCleanup(p.stop)
        accounts.init_db();monitoring.init_db();self.user=accounts.register_user(email="a@example.test",password="password-test",name="A")
    async def test_deep_link_is_single_use_private_and_user_bound(self):
        with patch("src.parcers.notifications.bot_call",AsyncMock(return_value={"username":"my_test_bot"})):
            link=await notifications.connect_link(self.user["id"])
        token=link["url"].split("start=")[1];message={"text":"/start "+token,"chat":{"type":"group","id":11},"from":{"id":11,"username":"alice"}}
        self.assertIsNone(notifications.bind(message));message["chat"]["type"]="private"
        self.assertIn("подключён",notifications.bind(message));self.assertIn("устарела",notifications.bind(message))
        self.assertTrue(notifications.settings(self.user["id"])["telegram_connected"])
        notifications.disconnect(self.user["id"]);self.assertFalse(notifications.settings(self.user["id"])["telegram_connected"])
    async def test_only_owners_verified_mailbox_receives_alert(self):
        token=account_security.issue(self.user["id"],"verify");account_security.consume(token,"verify")
        with patch("src.parcers.mailer.settings",return_value={"ready":True}):
            notifications.update_settings(self.user["id"],email_enabled=True)
            monitor=monitoring.create_monitor(query="A",title="A",marketplace="Ozon",product_url="https://ozon.ru/p/1",interval_seconds=900,user_id=self.user["id"],target_price=100,notify_email=True)
            monitoring.record_check(monitor["id"],price=90,currency="RUB",status="ok")
            item=notifications.claim()
            with patch("src.parcers.mailer.send") as send:await notifications.deliver_one(item)
            self.assertEqual(send.call_args.args[0],"a@example.test")
            with accounts._connect() as db:self.assertEqual(db.execute("SELECT status FROM notification_deliveries").fetchone()[0],"sent")
    async def test_failed_delivery_remains_retryable(self):
        token=account_security.issue(self.user["id"],"verify");account_security.consume(token,"verify")
        with patch("src.parcers.mailer.settings",return_value={"ready":True}):
            notifications.update_settings(self.user["id"],email_enabled=True)
            monitor=monitoring.create_monitor(query="A",title="A",marketplace="Ozon",product_url="https://ozon.ru/p/1",interval_seconds=900,user_id=self.user["id"],target_price=100,notify_email=True)
            monitoring.record_check(monitor["id"],price=90,currency="RUB",status="ok");item=notifications.claim()
            with patch("src.parcers.mailer.send",side_effect=RuntimeError("offline")):await notifications.deliver_one(item)
            with accounts._connect() as db:row=db.execute("SELECT * FROM notification_deliveries").fetchone();self.assertEqual(row["status"],"pending");self.assertGreater(row["next_at"],time.time())
    async def test_chat_cannot_be_rebound_to_another_account(self):
        other=accounts.register_user(email="b@example.test",password="password-test",name="B")
        with patch("src.parcers.notifications.bot_call",AsyncMock(return_value={"username":"my_test_bot"})):
            first=await notifications.connect_link(self.user["id"]);second=await notifications.connect_link(other["id"])
        def message(url):return {"text":"/start "+url.split("start=")[1],"chat":{"type":"private","id":99},"from":{"id":99,"username":"alice"}}
        notifications.bind(message(first["url"]))
        self.assertIn("другому аккаунту",notifications.bind(message(second["url"])))
        self.assertFalse(notifications.settings(other["id"])["telegram_connected"])
    async def test_expired_link_cannot_connect_a_chat(self):
        with patch("src.parcers.notifications.bot_call",AsyncMock(return_value={"username":"my_test_bot"})):link=await notifications.connect_link(self.user["id"])
        with accounts._connect() as db:db.execute("UPDATE telegram_links SET expires_at=0")
        text=notifications.bind({"text":"/start "+link["url"].split("start=")[1],"chat":{"type":"private","id":99},"from":{"id":99}})
        self.assertIn("устарела",text);self.assertFalse(notifications.settings(self.user["id"])["telegram_connected"])
