from asyncio import gather, create_task, sleep as asleep, Event
from asyncio.subprocess import PIPE
from os import path as ospath
from aiofiles.os import remove as aioremove
from traceback import format_exc
from base64 import urlsafe_b64encode
from time import time
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import logging

from bot import bot, bot_loop, Var, ani_cache, ffQueue, ffLock, ff_queued
from .tordownload import TorDownloader
from .database import db
from .func_utils import getfeed, encode, editMessage, sendMessage, convertBytes
from .text_utils import TextEditor
from .ffencoder import FFEncoder
from .tguploader import TgUploader
from .reporter import rep

# Configure a basic logger that only writes to console
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

btn_formatter = {
    '1080': '𝟭𝟬𝟴𝟬𝗽',
    '720': '𝟳𝟮𝟬𝗽',
    '480': '𝟰𝟴𝟬𝗽',
    '360': '𝟯𝟲𝟬𝗽'
}

async def fetch_animes():
    await rep.report("Fetch Animes Started !!", "info")
    while True:
        await asleep(60)
        if ani_cache['fetch_animes']:
            for link in Var.RSS_ITEMS:
                if (info := await getfeed(link, 0)):
                    bot_loop.create_task(get_animes(info.title, info.link))

async def get_animes(name, torrent, force=False):
    try:
        aniInfo = TextEditor(name)
        # Check if load_anilist succeeds, skip if it returns False
        if not await aniInfo.load_anilist():
            # Use custom logger to avoid channel
            logger.warning(f"Skipping torrent download for {name} due to no API data")
            return

        # Check and fallback if adata or pdata is None after successful load_anilist
        if aniInfo.adata is None or not isinstance(aniInfo.adata, dict):
            aniInfo.adata = {"id": None, "title": {"romaji": name.split("[", 1)[0].strip()}}
            await rep.report(f"adata is None or invalid for {name}, using fallback", "warning")
        if aniInfo.pdata is None or not isinstance(aniInfo.pdata, dict):
            aniInfo.pdata = {"episode_number": None}
            await rep.report(f"pdata is None or invalid for {name}, using fallback", "warning")
        ani_id, ep_no = aniInfo.adata.get('id'), aniInfo.pdata.get("episode_number")

        if ani_id not in ani_cache['ongoing']:
            ani_cache['ongoing'].add(ani_id)
        elif not force:
            return

        if not force and ani_id in ani_cache['completed']:
            return

        if force or (not (ani_data := await db.getAnime(ani_id)) \
            or (ani_data and not (qual_data := ani_data.get("episodes", {}).get(ep_no))) \
            or (ani_data and qual_data and not all(qual_data.get(q, False) for q in Var.QUALS))):

            if "[Batch]" in name:
                await rep.report(f"Torrent Skipped!\n\n{name}", "warning")
                return

            await rep.report(f"New Anime Torrent Found!\n\n{name}", "info")
            poster = await aniInfo.get_poster()
            caption = await aniInfo.get_caption()
            if not caption or not isinstance(caption, str):
                caption = f"‣ <b>Anime Name :</b> <b><i>{name or 'Unknown'}</i></b>\n\n<i>No caption available.</i>"
                await rep.report(f"Invalid caption for {name}, using fallback", "warning")
            if poster:
                post_msg = await bot.send_photo(Var.MAIN_CHANNEL, photo=poster, caption=caption)
            else:
                await rep.report(f"No valid poster found for {name}, sending caption only", "warning")
                post_msg = await bot.send_message(Var.MAIN_CHANNEL, text=caption)

            await asleep(1.5)
            stat_msg = await sendMessage(Var.MAIN_CHANNEL, f"‣ <b>Anime Name :</b> <b><i>{name or 'Unknown'}</i></b>\n\n<i>Downloading...</i>")
            dl = await TorDownloader("./downloads").download(torrent, name)

            if not dl or not ospath.exists(dl):
                await rep.report(f"File Download Incomplete, Try Again", "error")
                await editMessage(stat_msg, f"‣ <b>Anime Name :</b> <b><i>{name or 'Unknown'}</i></b>\n\n<i>Download Failed.</i>")
                await stat_msg.delete()
                return

            post_id = post_msg.id
            ffEvent = Event()
            ff_queued[post_id] = ffEvent

            if ffLock.locked():
                text = f"‣ <b>Anime Name :</b> <b><i>{name or 'Unknown'}</i></b>\n\n<i>Queued to Encode...</i>"
                if not text.strip():
                    text = "⚠️ Unable to update status: Queuing failed."
                    await rep.report(f"Empty text detected for stat_msg queue update: {name}", "warning")
                await editMessage(stat_msg, text)
                await rep.report("Added Task to Queue...", "info")

            await ffQueue.put(post_id)
            await ffEvent.wait()
            await ffLock.acquire()

            try:
                btns = []
                me = await bot.get_me()
                bot_username = me.username

                for qual in Var.QUALS:
                    filename = await aniInfo.get_upname(qual)

                    if not filename:
                        await rep.report(f"[ERROR] Filename returned None for `{name}` ({qual}) - skipping encode", "error")
                        continue

                    text = f"‣ <b>Anime Name :</b> <b><i>{filename}</i></b>\n\n<i>Ready to Encode...</i>"
                    if not text.strip():
                        text = f"⚠️ Unable to update status for {qual}: Invalid data."
                        await rep.report(f"Empty text detected for stat_msg encode update: {name} ({qual})", "warning")
                    await editMessage(stat_msg, text)
                    await asleep(1.5)
                    await rep.report("Starting Encode...", "info")

                    out_path = await FFEncoder(stat_msg, dl, filename, qual).start_encode()

                    if not out_path or not ospath.exists(out_path):
                        await rep.report("[ERROR] Encoding failed or output not found!", "error")
                        await editMessage(stat_msg, f"‣ <b>Anime Name :</b> <b><i>{name or 'Unknown'}</i></b>\n\n<i>Encoding Failed.</i>")
                        await stat_msg.delete()
                        return

                    await rep.report("Succesfully Compressed. Uploading...", "info")
                    text = f"‣ <b>Anime Name :</b> <b><i>{filename}</i></b>\n\n<i>Ready to Upload...</i>"
                    if not text.strip():
                        text = f"⚠️ Unable to update status for upload: Invalid data."
                        await rep.report(f"Empty text detected for stat_msg upload update: {name} ({qual})", "warning")
                    await editMessage(stat_msg, text)
                    await asleep(1.5)

                    msg = await TgUploader(stat_msg).upload(out_path, qual)
                    msg_id = msg.id
                    file_size = getattr(msg.document, "file_size", None) or getattr(msg.video, "file_size", 0)
                    link = f"https://telegram.me/{bot_username}?start={await encode('get-'+str(msg_id * abs(Var.FILE_STORE)))}"

                    if post_msg:
                        if len(btns) != 0 and len(btns[-1]) == 1:
                            btns[-1].insert(1, InlineKeyboardButton(f"{btn_formatter[qual]} - {convertBytes(file_size)}", url=link))
                        else:
                            btns.append([InlineKeyboardButton(f"{btn_formatter[qual]} - {convertBytes(file_size)}", url=link)])
                        # Use original caption with fallback
                        edit_text = post_msg.caption.html if post_msg.caption and post_msg.caption.html else f"‣ <b>Anime Name :</b> <b><i>{name or 'Unknown'}</i></b>"
                        if not edit_text.strip():
                            edit_text = f"⚠️ Unable to update post: No valid caption."
                            await rep.report(f"Empty caption detected for post_msg update: {name}", "warning")
                        await editMessage(post_msg, edit_text, InlineKeyboardMarkup(btns))

                    await db.saveAnime(ani_id, ep_no, qual, post_id)
                    bot_loop.create_task(extra_utils(msg_id, out_path))
            finally:
                ffLock.release()

            await stat_msg.delete()
            await aioremove(dl)

        ani_cache['completed'].add(ani_id)

    except Exception as error:
        await rep.report(format_exc(), "error")

async def extra_utils(msg_id, out_path):
    msg = await bot.get_messages(Var.FILE_STORE, message_ids=msg_id)

    if Var.BACKUP_CHANNEL != 0:
        for chat_id in Var.BACKUP_CHANNEL.split():
            await msg.copy(int(chat_id))
