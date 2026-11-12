"""SMTP transport: no message or action token is exposed through a public API."""
from email.message import EmailMessage
from email.utils import parseaddr
import os
import smtplib
import ssl
import logging
from urllib.parse import urlparse


def settings():
    host=os.getenv("MULTIMARKET_SMTP_HOST","").strip();sender=os.getenv("MULTIMARKET_SMTP_FROM","").strip()
    if not host or not sender:return None
    security=os.getenv("MULTIMARKET_SMTP_SECURITY","starttls").strip().lower()
    if security not in {"ssl","starttls","none"} or (security=="none" and host not in {"localhost","127.0.0.1","::1"}):return None
    if "\r" in sender or "\n" in sender or "@" not in parseaddr(sender)[1]:return None
    try:port=int(os.getenv("MULTIMARKET_SMTP_PORT","465" if security=="ssl" else "587"))
    except ValueError:return None
    if not 1<=port<=65535:return None
    return {"host":host,"port":port,"sender":sender,"security":security,"username":os.getenv("MULTIMARKET_SMTP_USERNAME",""),"password":os.getenv("MULTIMARKET_SMTP_PASSWORD","")}


def public_url():
    url=os.getenv("MULTIMARKET_PUBLIC_URL","http://localhost:8000").strip().rstrip("/");p=urlparse(url)
    try:port=p.port
    except ValueError as exc:raise RuntimeError("Адрес сайта для писем не настроен") from exc
    if port is not None and not 1<=port<=65535:raise RuntimeError("Адрес сайта для писем не настроен")
    if not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in {"","/"} or (p.scheme!="https" and not(p.scheme=="http" and p.hostname in {"localhost","127.0.0.1","::1"})):
        raise RuntimeError("Адрес сайта для писем не настроен")
    return url


def send(recipient,subject,text,message_id=None):
    config=settings()
    if not config:raise RuntimeError("Отправка писем пока недоступна. Попробуйте позже.")
    msg=EmailMessage();msg["From"]=config["sender"];msg["To"]=recipient;msg["Subject"]=subject
    if message_id:msg["Message-ID"]="<"+message_id+"@multimarket>"
    msg.set_content(text)
    try:
        ctor=smtplib.SMTP_SSL if config["security"]=="ssl" else smtplib.SMTP
        kwargs={"timeout":10}
        if config["security"]=="ssl":kwargs["context"]=ssl.create_default_context()
        with ctor(config["host"],config["port"],**kwargs) as client:
            if config["security"]=="starttls":client.starttls(context=ssl.create_default_context())
            if config["username"]:client.login(config["username"],config["password"])
            client.send_message(msg)
    except (smtplib.SMTPException,OSError) as exc:
        raise RuntimeError("Не удалось отправить письмо. Попробуйте позже.") from exc


def action_email(user,purpose,token):
    link=public_url()+("/reset-password" if purpose=="reset" else "/confirm-email")+"#token="+token
    label="Сброс пароля" if purpose=="reset" else "Подтверждение почты"
    lifetime="30 минут" if purpose=="reset" else "24 часа"
    send(user["email"],"MultiMarket — "+label,f"{label}\n\nПерейдите по ссылке: {link}\n\nСсылка действует {lifetime} и используется один раз. Если вы не запрашивали письмо, проигнорируйте его.")


def background_action_email(user,purpose,token):
    try:action_email(user,purpose,token)
    except RuntimeError:logging.getLogger(__name__).warning("Account action email delivery failed")
