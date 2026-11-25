"""Optional auto-archive for authorized Telegram channel uploads.

Set AUTO_ARCHIVE_SOURCE to the source channel ID and AUTO_ARCHIVE_ENABLED=true.
Copies posts to the configured database/archive channel, deduplicates by file_unique_id,
and reports results to OWNER_ID. It does not generate public share links."""
import os
import logging
from pyrogram import filters
from pyrogram.types import Message
from bot import Bot
from config import CHANNEL_ID, OWNER_ID
from database.database import db

log = logging.getLogger(__name__)
ENABLED = os.getenv("AUTO_ARCHIVE_ENABLED", "true").lower() in ("1", "true", "yes")
SOURCE_ID = int(os.getenv("AUTO_ARCHIVE_SOURCE", "-1002293652266") or 0)
archive_records = db.database["auto_archive_records"]

def get_media(message: Message):
    for field in ("document", "video", "audio", "animation", "photo"):
        obj = getattr(message, field, None)
        if obj:
            return obj, field
    return None, None

@Bot.on_message(filters.channel & filters.incoming)
async def auto_archive_channel_post(client: Bot, message: Message):
    if not ENABLED or not SOURCE_ID or message.chat.id != SOURCE_ID:
        return
    media, kind = get_media(message)
    if not media:
        return
    unique_id = getattr(media, "file_unique_id", None)
    if unique_id:
        existing = await archive_records.find_one({"file_unique_id": unique_id})
        if existing:
            try:
                await client.send_message(OWNER_ID, f"⏭️ Duplicate skipped: {message.chat.title or message.chat.id} / message {message.id}")
            except Exception:
                pass
            return
    try:
        archived = await message.copy(chat_id=CHANNEL_ID, disable_notification=True)
        record = {
            "file_unique_id": unique_id,
            "source_chat_id": message.chat.id,
            "source_message_id": message.id,
            "archive_chat_id": CHANNEL_ID,
            "archive_message_id": archived.id,
            "media_type": kind,
            "file_name": getattr(media, "file_name", None),
            "file_size": getattr(media, "file_size", None),
            "caption": message.caption or "",
        }
        if unique_id:
            await archive_records.update_one({"file_unique_id": unique_id}, {"$set": record}, upsert=True)
        else:
            await archive_records.insert_one(record)
        try:
            size = getattr(media, "file_size", 0) or 0
            size_text = f"{size / (1024**2):.2f} MB" if size else "unknown"
            name = getattr(media, "file_name", None) or kind
            await client.send_message(OWNER_ID, f"✅ Archived\nType: {kind}\nName: {name}\nSize: {size_text}\nSource message: {message.id}")
        except Exception:
            pass
    except Exception as exc:
        log.exception("Auto-archive failed")
        try:
            await client.send_message(OWNER_ID, f"⚠️ Auto-archive failed for message {message.id}: {exc}")
        except Exception:
            pass
