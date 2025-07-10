from os import path as ospath
from aiofiles import open as aiopen
from aiofiles.os import path as aiopath, remove as aioremove, mkdir

from aiohttp import ClientSession
from torrentp import TorrentDownloader
from bot import LOGS
from bot.core.func_utils import handle_logs


class TorDownloader:
    def __init__(self, path="."):
        self.__downdir = path
        self.__torpath = "torrents/"

    @handle_logs
    async def download(self, torrent, name=None):
        if torrent.startswith("magnet:"):
            LOGS.info("🔗 Magnet detected, starting download.")
            torp = TorrentDownloader(torrent, self.__downdir)
            await torp.start_download()

            # Fallback name if not provided
            try:
                final_name = name or torp._torrent_info._info.name()
            except Exception:
                final_name = "Unknown"

            return ospath.join(self.__downdir, final_name)

        elif torfile := await self.get_torfile(torrent):
            LOGS.info(f"📥 Torrent file downloaded: {torfile}")
            torp = TorrentDownloader(torfile, self.__downdir)
            await torp.start_download()
            await aioremove(torfile)

            try:
                final_name = torp._torrent_info._info.name()
            except Exception:
                final_name = "Unknown"

            return ospath.join(self.__downdir, final_name)

        else:
            LOGS.warning("⚠️ Invalid torrent URL or download failed.")
            return ""

    @handle_logs
    async def get_torfile(self, url):
        if not await aiopath.isdir(self.__torpath):
            await mkdir(self.__torpath)

        tor_name = url.split('/')[-1]
        des_dir = ospath.join(self.__torpath, tor_name)

        try:
            async with ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        async with aiopen(des_dir, 'wb') as file:
                            async for chunk in response.content.iter_any():
                                await file.write(chunk)
                        return des_dir
        except Exception as e:
            LOGS.error(f"❌ Failed to download .torrent file: {e}")

        return None