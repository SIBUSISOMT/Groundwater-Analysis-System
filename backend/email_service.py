"""
email_service.py — HydroCore Transactional Email
Configure via env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL, APP_BASE_URL
"""
import os, logging, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST  = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT  = int(os.getenv('SMTP_PORT', 587))
SMTP_USER  = os.getenv('SMTP_USER', '')
SMTP_PASS  = os.getenv('SMTP_PASSWORD', '')
FROM_EMAIL = os.getenv('FROM_EMAIL', SMTP_USER) or 'noreply@hydrocore.local'
BASE_URL   = os.getenv('APP_BASE_URL', 'http://localhost:5000')

_BTN_BLUE   = 'background:linear-gradient(135deg,#3b82f6,#2563eb)'
_BTN_PURPLE = 'background:linear-gradient(135deg,#7c3aed,#6d28d9)'

def _send(to_email: str, subject: str, html: str, text: str = '') -> bool:
    if not SMTP_USER or not SMTP_PASS:
        logger.warning('Email not configured (SMTP_USER/SMTP_PASSWORD missing). Would send to %s: %s', to_email, subject)
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        if text:
            msg.attach(MIMEText(text, 'plain'))
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.ehlo(); s.starttls(); s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(FROM_EMAIL, to_email, msg.as_string())
        logger.info('Email sent to %s: %s', to_email, subject)
        return True
    except Exception as exc:
        logger.error('Email send failed to %s: %s', to_email, exc)
        return False

def _card(header_style: str, header_content: str, body: str) -> str:
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f8fafc;padding:32px;">
<div style="max-width:560px;margin:0 auto;background:white;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
  <div style="{header_style};padding:32px 32px 24px;">{header_content}</div>
  <div style="padding:32px;">{body}</div>
</div></body></html>"""

def _setup_url(token: str) -> str:
    return f'{BASE_URL}/frontend/public/setup_account.html?token={token}'

def send_user_setup_email(to_email: str, username: str, setup_token: str, created_by: str = 'Administrator') -> bool:
    url = _setup_url(setup_token)
    header = f'<h1 style="color:white;margin:0;font-size:22px;">Welcome to HydroCore</h1><p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:14px;">National Groundwater Analysis Platform</p>'
    body = f"""<p style="color:#374151;margin:0 0 16px;">Hi <strong>{username}</strong>,</p>
<p style="color:#6b7280;line-height:1.6;margin:0 0 24px;"><strong>{created_by}</strong> has created a HydroCore account for you. Set up your password and two-factor authentication to get started.</p>
<div style="text-align:center;margin:32px 0;"><a href="{url}" style="{_BTN_BLUE};color:white;text-decoration:none;padding:14px 32px;border-radius:10px;font-weight:600;font-size:15px;display:inline-block;">Set Up My Account</a></div>
<p style="color:#9ca3af;font-size:12px;text-align:center;">This link expires in 72 hours. If unexpected, ignore this email.</p>
<hr style="border:none;border-top:1px solid #f3f4f6;margin:24px 0;">
<p style="color:#d1d5db;font-size:11px;text-align:center;">HydroCore v2.0 &middot; National Groundwater Analysis Platform</p>"""
    html = _card(f'{_BTN_BLUE}', header, body)
    text = f"Hi {username},\n\n{created_by} created a HydroCore account for you.\n\nSet up your account:\n{url}\n\nExpires in 72 hours."
    return _send(to_email, 'Welcome to HydroCore — Set Up Your Account', html, text)

def send_tenant_admin_setup_email(to_email: str, username: str, org_name: str, setup_token: str) -> bool:
    url = _setup_url(setup_token)
    header = f'<h1 style="color:white;margin:0;font-size:22px;">HydroCore Administrator Account</h1><p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:14px;">{org_name}</p>'
    body = f"""<p style="color:#374151;margin:0 0 16px;">Hi <strong>{username}</strong>,</p>
<p style="color:#6b7280;line-height:1.6;margin:0 0 16px;">You have been appointed as the <strong>Organisation Administrator</strong> for <strong>{org_name}</strong> on HydroCore.</p>
<p style="color:#6b7280;line-height:1.6;margin:0 0 24px;">As administrator, you can manage users, assign roles, and oversee platform access for your organisation.</p>
<div style="text-align:center;margin:32px 0;"><a href="{url}" style="{_BTN_PURPLE};color:white;text-decoration:none;padding:14px 32px;border-radius:10px;font-weight:600;font-size:15px;display:inline-block;">Set Up My Administrator Account</a></div>
<p style="color:#9ca3af;font-size:12px;text-align:center;">This link expires in 72 hours.</p>"""
    html = _card(f'{_BTN_PURPLE}', header, body)
    text = f"Hi {username},\n\nYou are the administrator for {org_name} on HydroCore.\n\nSet up your account:\n{url}\n\nExpires in 72 hours."
    return _send(to_email, f'HydroCore — Administrator Account for {org_name}', html, text)

def send_system_admin_setup_email(to_email: str, username: str, setup_token: str) -> bool:
    url = _setup_url(setup_token)
    header = '<h1 style="color:white;margin:0;font-size:22px;">HydroCore System Administration</h1><p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:14px;">Super Administrator Account</p>'
    body = f"""<p style="color:#374151;margin:0 0 16px;">Hi <strong>{username}</strong>,</p>
<p style="color:#6b7280;line-height:1.6;margin:0 0 24px;">A HydroCore <strong>System Administrator</strong> account has been created for you. This account provides access to the full system administration portal where you can manage all tenants and organisations.</p>
<div style="text-align:center;margin:32px 0;"><a href="{url}" style="background:linear-gradient(135deg,#0f172a,#1e293b);color:white;text-decoration:none;padding:14px 32px;border-radius:10px;font-weight:600;font-size:15px;display:inline-block;">Set Up System Admin Account</a></div>
<p style="color:#9ca3af;font-size:12px;text-align:center;">This link expires in 72 hours. Keep this email confidential.</p>"""
    html = _card('background:linear-gradient(135deg,#0f172a,#1e293b)', header, body)
    text = f"Hi {username},\n\nA HydroCore System Administrator account was created for you.\n\nSet up your account:\n{url}\n\nExpires in 72 hours."
    return _send(to_email, 'HydroCore — System Administrator Account Setup', html, text)
