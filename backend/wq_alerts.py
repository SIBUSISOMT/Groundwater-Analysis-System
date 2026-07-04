"""
wq_alerts.py — HydroCore Water Quality Alert Dispatch
======================================================
Sends email and WhatsApp notifications for threshold breaches.
Uses stdlib only: urllib.request, base64, smtplib.
Configured via env vars (no new packages required).

Env vars:
  TWILIO_ACCOUNT_SID   — Twilio account SID
  TWILIO_AUTH_TOKEN    — Twilio auth token
  TWILIO_WA_FROM       — WhatsApp sender (e.g. 'whatsapp:+14155238886')
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL  — same as email_service
"""

import base64
import logging
import os
import urllib.request
import urllib.parse
import urllib.error
from email_service import _send as _send_email

logger = logging.getLogger(__name__)

_TWILIO_SID   = os.getenv('TWILIO_ACCOUNT_SID', '')
_TWILIO_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
_TWILIO_FROM  = os.getenv('TWILIO_WA_FROM', '')


def _send_whatsapp(to_number: str, body: str) -> bool:
    """
    Send a WhatsApp message via Twilio REST API using stdlib only.
    to_number must start with 'whatsapp:+' or '+'.
    """
    if not (_TWILIO_SID and _TWILIO_TOKEN and _TWILIO_FROM):
        logger.warning('WhatsApp not configured — TWILIO_* env vars missing. Would send to %s', to_number)
        return False

    if not to_number.startswith('whatsapp:'):
        to_number = f'whatsapp:{to_number}'

    url   = f'https://api.twilio.com/2010-04-01/Accounts/{_TWILIO_SID}/Messages.json'
    creds = base64.b64encode(f'{_TWILIO_SID}:{_TWILIO_TOKEN}'.encode()).decode()

    data = urllib.parse.urlencode({
        'From': _TWILIO_FROM,
        'To':   to_number,
        'Body': body,
    }).encode('utf-8')

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            'Authorization': f'Basic {creds}',
            'Content-Type':  'application/x-www-form-urlencoded',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            ok = 200 <= status < 300
            if ok:
                logger.info('WhatsApp sent to %s', to_number)
            else:
                logger.error('WhatsApp HTTP %s to %s', status, to_number)
            return ok
    except urllib.error.HTTPError as e:
        logger.error('WhatsApp HTTPError %s to %s: %s', e.code, to_number, e.read().decode('utf-8', errors='replace'))
        return False
    except Exception as exc:
        logger.error('WhatsApp send error to %s: %s', to_number, exc)
        return False


def _build_alert_message(indicator_name: str, unit: str, measured_val,
                          threshold_value: float, threshold_type: str,
                          station_name: str, reading_date: str) -> str:
    direction = 'above' if threshold_type == 'ABOVE' else 'below'
    val_fmt   = f'{measured_val:.4g}' if measured_val is not None else 'N/A'
    unit_str  = f' {unit}' if unit else ''
    return (
        f'[HydroCore ALERT] Water quality breach at {station_name} on {reading_date}.\n'
        f'{indicator_name}: {val_fmt}{unit_str} — {direction} threshold of {threshold_value}{unit_str}.\n'
        f'Immediate review recommended.'
    )


def _build_alert_html(indicator_name: str, unit: str, measured_val,
                       threshold_value: float, threshold_type: str,
                       station_name: str, reading_date: str) -> str:
    direction = 'above' if threshold_type == 'ABOVE' else 'below'
    val_fmt   = f'{measured_val:.4g}' if measured_val is not None else 'N/A'
    unit_str  = f' {unit}' if unit else ''

    return f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px;">
<div style="max-width:520px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,0.08);">
  <div style="background:linear-gradient(135deg,#dc2626,#b91c1c);padding:24px 28px 20px;">
    <h1 style="color:white;margin:0;font-size:18px;">&#9888; Water Quality Alert</h1>
    <p style="color:rgba(255,255,255,0.85);margin:4px 0 0;font-size:13px;">HydroCore Monitoring System</p>
  </div>
  <div style="padding:28px;">
    <p style="color:#374151;margin:0 0 16px;">A water quality exceedance has been detected:</p>
    <table style="width:100%;border-collapse:collapse;margin:0 0 20px;">
      <tr style="background:#fef2f2;"><td style="padding:8px 12px;font-weight:600;color:#374151;border:1px solid #fee2e2;">Station</td><td style="padding:8px 12px;color:#111827;border:1px solid #fee2e2;">{station_name}</td></tr>
      <tr><td style="padding:8px 12px;font-weight:600;color:#374151;border:1px solid #fee2e2;">Date</td><td style="padding:8px 12px;color:#111827;border:1px solid #fee2e2;">{reading_date}</td></tr>
      <tr style="background:#fef2f2;"><td style="padding:8px 12px;font-weight:600;color:#374151;border:1px solid #fee2e2;">Parameter</td><td style="padding:8px 12px;color:#111827;border:1px solid #fee2e2;">{indicator_name}</td></tr>
      <tr><td style="padding:8px 12px;font-weight:600;color:#374151;border:1px solid #fee2e2;">Measured Value</td><td style="padding:8px 12px;color:#dc2626;font-weight:700;border:1px solid #fee2e2;">{val_fmt}{unit_str}</td></tr>
      <tr style="background:#fef2f2;"><td style="padding:8px 12px;font-weight:600;color:#374151;border:1px solid #fee2e2;">Exceedance</td><td style="padding:8px 12px;color:#dc2626;border:1px solid #fee2e2;">{direction.capitalize()} threshold ({threshold_value}{unit_str})</td></tr>
    </table>
    <p style="color:#dc2626;font-weight:600;margin:0;">Immediate review is recommended.</p>
    <hr style="border:none;border-top:1px solid #f3f4f6;margin:20px 0;">
    <p style="color:#d1d5db;font-size:11px;text-align:center;">HydroCore Water Quality Monitoring &middot; Automated Alert</p>
  </div>
</div>
</body></html>"""


def dispatch_alert(db_query_fn, org_id: int, reading_id: int, indicator_id: int,
                   indicator_code: str, indicator_name: str, unit: str,
                   measured_val, threshold_value: float, threshold_type: str,
                   station_name: str, reading_date: str) -> list:
    """
    Find matching active alert configurations and dispatch email + WhatsApp.

    db_query_fn: callable — the _q() helper from wq_bp.py
    Returns list of log dicts showing what was dispatched.
    """
    # Fetch matching alert configs
    configs = db_query_fn(
        """
        SELECT alert_id, alert_email, alert_whatsapp
        FROM dbo.WQ_Alert_Config
        WHERE org_id = ?
          AND indicator_id = ?
          AND is_active = 1
          AND threshold_type = ?
          AND (station_id IS NULL OR station_id = (
                SELECT station_id FROM dbo.WQ_Readings WHERE reading_id = ?))
        """,
        [org_id, indicator_id, threshold_type, reading_id]
    )

    if not configs:
        return []

    plain_msg = _build_alert_message(
        indicator_name, unit, measured_val, threshold_value,
        threshold_type, station_name, reading_date
    )
    html_msg = _build_alert_html(
        indicator_name, unit, measured_val, threshold_value,
        threshold_type, station_name, reading_date
    )
    subject = f'[HydroCore] {indicator_name} breach at {station_name}'

    log_entries = []

    for row in configs:
        alert_id, email_to, wa_to = row

        if email_to:
            ok = _send_email(email_to, subject, html_msg, plain_msg)
            status = 'sent' if ok else 'failed'
            _log_alert(db_query_fn, org_id, alert_id, reading_id, indicator_id,
                       measured_val, 'email', email_to, status, plain_msg)
            log_entries.append({'channel': 'email', 'recipient': email_to, 'status': status})

        if wa_to:
            ok = _send_whatsapp(wa_to, plain_msg)
            status = 'sent' if ok else 'failed'
            _log_alert(db_query_fn, org_id, alert_id, reading_id, indicator_id,
                       measured_val, 'whatsapp', wa_to, status, plain_msg)
            log_entries.append({'channel': 'whatsapp', 'recipient': wa_to, 'status': status})

    return log_entries


def _log_alert(db_query_fn, org_id, alert_id, reading_id, indicator_id,
               measured_val, channel, recipient, status, body):
    try:
        db_query_fn(
            """
            INSERT INTO dbo.WQ_Alert_Log
                (org_id, alert_id, reading_id, indicator_id, measured_val,
                 channel, recipient, status, message_body)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            [org_id, alert_id, reading_id, indicator_id, measured_val,
             channel, recipient, status, body],
            fetch=False, commit=True
        )
    except Exception as exc:
        logger.error('Failed to log alert: %s', exc)
