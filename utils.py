import os
import re
import mimetypes
from bs4 import BeautifulSoup
from libratom.lib.pff import PffArchive

def decode_if_bytes(value):
    return value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else value

def extract_header_field(headers, field_name):
    headers = decode_if_bytes(headers or "")
    pattern = rf"^{field_name}:\s*(.*)$"
    match = re.search(pattern, headers, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""

def safe_getattr(obj, attr, default=""):
    try:
        return decode_if_bytes(getattr(obj, attr, default))
    except Exception:
        return decode_if_bytes(default)

def get_attachment_info(attachment):
    try:
        # Try multiple ways to get the name
        name = None
        if hasattr(attachment, 'name') and attachment.name:
            name = decode_if_bytes(attachment.name)
        elif hasattr(attachment, 'long_filename') and attachment.long_filename:
            name = decode_if_bytes(attachment.long_filename)
        elif hasattr(attachment, 'filename') and attachment.filename:
            name = decode_if_bytes(attachment.filename)
        else:
            name = "Unnamed"

        ext = name.split('.')[-1].lower() if '.' in name else ''
        mime_type, _ = mimetypes.guess_type(name)
        mime_type = mime_type or ext

        size = attachment.get_size()
        data = attachment.read_buffer(size) if size > 0 else b""

        return {
            "name": name,
            "size": len(data),
            "type": mime_type,
            "data": data
        }

    except Exception as e:
        print(f"Attachment read error: {e}")
        return None


def extract_emails(pst_file):
    emails = []
    with PffArchive(pst_file) as archive:
        for message in archive.messages():
            subject = safe_getattr(message, "subject", "")
            sender = safe_getattr(message, "sender_name", "")
            sender_email = safe_getattr(message, "sender_email_address", "")
            sent_time = safe_getattr(message, "client_submit_time", "")
            headers = safe_getattr(message, "transport_headers", "")
            to = extract_header_field(headers, "To")
            cc = extract_header_field(headers, "Cc")

            plain_body = safe_getattr(message, "plain_text_body", None)
            html_body = safe_getattr(message, "html_body", None)

            if plain_body:
                body = plain_body
            elif html_body:
                soup = BeautifulSoup(html_body, "html.parser")
                body = soup.get_text()
            else:
                body = ""

            attachments = []
            try:
            # Wrap number_of_attachments in try-except
               try:
                 num_attachments = message.number_of_attachments
               except Exception:
                 num_attachments = 0

               if num_attachments > 0:
                   for attachment in message.attachments:
                       att_info = get_attachment_info(attachment)
                       if att_info:
                           attachments.append(att_info)
            except Exception as e:
              print(f"Attachment error: {e}")


            emails.append({
                "subject": subject,
                "sender": f"{sender} <{sender_email}>",
                "to": to,
                "cc": cc,
                "sent_time": sent_time,
                "body": body,
                "attachments": attachments,
            })

    return emails

def search_emails(emails, query):
    if not query:
        return emails
    query = query.lower()
    results = []
    for email in emails:
        if (query in (email.get("subject") or "").lower() or
            query in (email.get("sender") or "").lower() or
            query in (email.get("to") or "").lower() or
            query in (email.get("cc") or "").lower() or
            query in (email.get("body") or "").lower()):
            results.append(email)
    return results      