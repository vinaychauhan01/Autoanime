from os import path as ospath
from aiofiles import open as aiopen
from aiofiles.os import path as aiopath, remove as aioremove, mkdir
from asyncio import sleep as asleep

from aiohttp import ClientSession
from torrentp import TorrentDownloader
from bot import LOGS
from bot.core.func_utils import handle_logs

class TorDownloader:
    def __init__(self, path="."):
        self.__downdir = path
        self.__torpath = "torrents/"
        self.__max_attempts = 5  # Max attempts to check progress
        self.__check_interval = 60  # Check every 60 seconds

    @handle_logs
    async def download(self, torrent, name=None):
        if torrent.startswith("magnet:"):
            LOGS.info("🔗 Magnet detected, starting download.")
            torp = TorrentDownloader(torrent, self.__downdir)
            await self._monitor_download(torp, name)
            try:
                final_name = name or torp._torrent_info._info.name()
            except Exception as e:
                LOGS.error(f"❌ Failed to get name from magnet torrent: {e}")
                final_name = "Unknown"
            return ospath.join(self.__downdir, final_name)

        elif torfile := await self.get_torfile(torrent):
            LOGS.info(f"📥 Torrent file downloaded: {torfile}")
            torp = TorrentDownloader(torfile, self.__downdir)
            try:
                await self._monitor_download(torp, name)
                if not hasattr(torp, '_torrent_info') or not torp._torrent_info._info:
                    raise RuntimeError("Invalid torrent info after download")
                final_name = torp._torrent_info._info.name()
            except Exception as e:
                LOGS.error(f"❌ Error processing torrent file {torfile}: {e}")
                await aioremove(torfile)
                return None
            await aioremove(torfile)
            return ospath.join(self.__downdir, final_name)

        else:
            LOGS.warning("⚠️ Invalid torrent URL or download failed.")
            return ""

    @handle_logs
    async def _monitor_download(self, torp, name):
        await torp.start_download()
        attempt = 0
        while attempt < self.__max_attempts:
            progress = await self._get_progress(torp)
            speed = await self._get_download_speed(torp)
            peers = await self._get_peer_count(torp)
            status = "seeding" if progress >= 100 else "downloading"
            LOGS.info(f"{progress}% complete (down: {speed:.1f} kB/s up: {await self._get_upload_speed(torp):.1f} kB/s peers: {peers}) {status}")
            if progress >= 100:
                return
            elif progress == 0 and speed < 1.0 and attempt > 2:  # Stalled if no progress and low speed after 3 checks
                LOGS.warning(f"⚠️ Torrent download stalled for {name or 'Unknown'}, aborting after {attempt} attempts")
                await torp.stop_download()  # Stop the download
                raise RuntimeError("Download stalled")
            await asleep(self.__check_interval)
            attempt += 1
        LOGS.warning(f"⚠️ Torrent download timed out for {name or 'Unknown'} after {self.__max_attempts} attempts")
        await torp.stop_download()
        raise RuntimeError("Download timed out")

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
                            content = await response.read()  # Read full content
                            if len(content) == 0:
                                raise ValueError("Empty torrent file downloaded")
                            # Check if bencode starts with 'd' (hex 64)
                            if content and content[0] != 100:  # 100 is ASCII for 'd'
                                LOGS.warning(f"⚠️ Torrent file {tor_name} may be invalid, does not start with 'd'")
                            await file.write(content)
                        return des_dir
        except Exception as e:
            LOGS.error(f"❌ Failed to download .torrent file: {e}")
            if await aiopath.exists(des_dir):
                await aioremove(des_dir)

        return None

    async def _get_progress(self, torp):
        # Placeholder: Implement based on torrentp API (e.g., torp.get_progress())
        # Return progress as percentage (0-100)
        try:
            return getattr(torp, 'get_progress', lambda: 0)() or 0
        except Exception:
            return 0

    async def _get_download_speed(self, torp):
        # Placeholder: Implement based on torrentp API (e.g., torp.get_download_rate())
        # Return speed in kB/s
        try:
            return getattr(torp, 'get_download_rate', lambda: 0)() / 1024 or 0.0
        except Exception:
            return 0.0

    async def _get_upload_speed(self, torp):
        # Placeholder: Implement based on torrentp API (e.g., torp.get_upload_rate())
        # Return speed in kB/s
        try:
            return getattr(torp, 'get_upload_rate', lambda: 0)() / 1024 or 0.0
        except Exception:
            return 0.0

    async def _get_peer_count(self, torp):
        # Placeholder: Implement based on torrentp API (e.g., torp.get_peer_count())
        # Return number of peers
        try:
            return getattr(torp, 'get_peer_count', lambda: 0)() or 0
        except Exception:
            return 0
