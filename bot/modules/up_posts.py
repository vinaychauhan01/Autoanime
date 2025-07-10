from os import execl, path as ospath
from sys import executable
from json import loads as jloads
from aiohttp import ClientSession

from bot import Var, bot, ffQueue
from bot.core.text_utils import TextEditor
from bot.core.reporter import rep

# Global to hold the schedule message for update
TD_SCHR = None

async def upcoming_animes():
    global TD_SCHR
    if Var.SEND_SCHEDULE:
        try:
            async with ClientSession() as ses:
                res = await ses.get("https://subsplease.org/api/?f=schedule&h=true&tz=Asia/Kolkata")
                aniContent = jloads(await res.text())["schedule"]

            text = "<b>📆 Today's Anime Releases Schedule [IST]</b>\n\n"
            for i in aniContent:
                aname = TextEditor(i["title"])
                await aname.load_anilist()
                title = aname.adata.get('title', {}).get('english') or i['title']
                text += f'''🕒 <a href="https://subsplease.org/shows/{i['page']}">{title}</a>\n    • <b>Time</b> : {i["time"]} hrs\n\n'''

            TD_SCHR = await bot.send_message(Var.MAIN_CHANNEL, text)
            await TD_SCHR.unpin()  # Unpin any existing pinned message if needed
        except Exception as err:
            await rep.report(str(err), "error")

    if not ffQueue.empty():
        await ffQueue.join()

    await rep.report("Auto Restarting..!!", "info")
    execl(executable, executable, "-m", "bot")


async def update_shdr(name, link):
    global TD_SCHR
    if TD_SCHR is not None:
        TD_lines = TD_SCHR.text.split('\n')
        for i, line in enumerate(TD_lines):
            if name.lower() in line.lower():
                TD_lines[i+2] = f"    • <b>Status :</b> ✅ <i>Uploaded</i>\n    • <b>Link :</b> <a href=\"{link}\">Download</a>"
                break
        await TD_SCHR.edit_text("\n".join(TD_lines), disable_web_page_preview=True)