from calendar import month_name
from datetime import datetime
from random import choice
from asyncio import sleep as asleep
from aiohttp import ClientSession, ClientError, ContentTypeError
from anitopy import parse
from xml.etree import ElementTree as ET

from bot import Var, bot
from .ffencoder import ffargs
from .func_utils import handle_logs
from .reporter import rep

CAPTION_FORMAT = """
<b>㊂ <i>{title}</i></b>
<b>╭┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅</b>
<b>⊙</b> <i>Genres:</i> <i>{genres}</i>
<b>⊙</b> <i>Season:</i> <i>{season}</i>
<b>⊙</b> <i>Status:</i> <i>RELEASING</i>
<b>⊙</b> <i>Source:</i> <i>Subsplease</i>
<b>⊙</b> <i>Episode:</i> <i>{ep_no}</i>
<b>⊙</b> <i>Audio: Japanese</i>
<b>⊙</b> <i>Subtitle: English</i>
<b>╰┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅</b>
╭┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅
⌬  <b><i>Powered By</i></b> ~ </i></b><b><i>{cred}</i></b>
╰┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅
"""

GENRES_EMOJI = {
    "Action": "👊", "Adventure": choice(['🪂', '🧗‍♀']), "Comedy": "🤣",
    "Drama": " 🎭", "Ecchi": choice(['💋', '🥵']), "Fantasy": choice(['🧞', '🧞‍ atualmente', '🧞‍♀', '🌗']),
    "Hentai": "🔞", "Horror": "☠", "Mahou Shoujo": "☯", "Mecha": "🤖", "Mystery": "🔮",
    "Psychological": "♟", "Romance": "💞", "Sci-Fi": "🛸",
    "Slice of Life": choice(['☘', '🍁']), "Sports": "⚽️", "Supernatural": "🫧", "Thriller": choice(['🥶', '🔪', '🤯'])
}

ANIME_GRAPHQL_QUERY = """
query ($id: Int, $search: String, $seasonYear: Int) {
    Media(id: $id, type: ANIME, format_not_in: [MOVIE, MUSIC, MANGA, NOVEL, ONE_SHOT], search: $search, seasonYear: $seasonYear) {
        id
        idMal
        title {
            romaji
            english
            native
        }
        type
        format
        status(version: 2)
        description(asHtml: false)
        startDate {
            year
            month
            day
        }
        endDate {
            year
            month
            day
        }
        season
        seasonYear
        episodes
        duration
        chapters
        volumes
        countryOfOrigin
        source
        hashtag
        trailer {
            id
            site
            thumbnail
        }
        updatedAt
        coverImage {
            large
        }
        bannerImage
        genres
        synonyms
        averageScore
        meanScore
        popularity
        trending
        favourites
        studios {
            nodes {
                name
                siteUrl
            }
        }
        isAdult
        nextAiringEpisode {
            airingAt
            timeUntilAiring
            episode
        }
        airingSchedule {
            edges {
                node {
                    airingAt
                    timeUntilAiring
                    episode
                }
            }
        }
        externalLinks {
            url
            site
        }
        siteUrl
    }
}
"""

class AniLister:
    def __init__(self, anime_name: str, year: int) -> None:
        self.__api = "https://graphql.anilist.co"
        self.__ani_name = anime_name
        self.__ani_year = year
        self.__vars = {'search': self.__ani_name, 'seasonYear': self.__ani_year}

    def __update_vars(self, year=True) -> None:
        if year:
            self.__ani_year -= 1
            self.__vars['seasonYear'] = self.__ani_year
        else:
            self.__vars = {'search': self.__ani_name}

    async def post_data(self):
        try:
            async with ClientSession() as sess:
                async with sess.post(
                    self.__api,
                    json={'query': ANIME_GRAPHQL_QUERY, 'variables': self.__vars},
                    timeout=15
                ) as resp:
                    if resp.status != 200:
                        return (resp.status, None, resp.headers)

                    if resp.content_type != "application/json":
                        raise ContentTypeError(
                            resp.request_info,
                            resp.history,
                            message=f"Unexpected content-type: {resp.content_type}"
                        )

                    return (resp.status, await resp.json(), resp.headers)

        except ContentTypeError as e:
            await rep.report(f"AniList JSON decode failed: {e}", "error")
            return (500, None, None)
        except ClientError as e:
            await rep.report(f"AniList client error: {e}", "error")
            return (503, None, None)
        except Exception as e:
            await rep.report(f"Unexpected AniList error: {e}", "error")
            return (500, None, None)

    @handle_logs
    async def get_kitsu_data(self):
        kitsu_api = f"https://kitsu.io/api/edge/anime?filter[text]={self.__ani_name}"
        try:
            async with ClientSession() as sess:
                async with sess.get(kitsu_api, timeout=10) as resp:
                    if resp.status != 200:
                        return {}

                    data = await resp.json()
                    if not data.get("data"):
                        return {}

                    anime = data["data"][0]["attributes"]
                    start_year, start_month, start_day = None, None, None
                    if anime.get("startDate"):
                        try:
                            start_year, start_month, start_day = map(int, anime["startDate"].split("-"))
                        except:
                            pass

                    return {
                        "title": {
                            "romaji": anime.get("canonicalTitle"),
                            "english": anime.get("titles", {}).get("en"),
                            "native": anime.get("titles", {}).get("ja_jp")
                        },
                        "genres": anime.get("genres") or [],
                        "startDate": {
                            "year": start_year,
                            "month": start_month,
                            "day": start_day
                        },
                        "episodes": anime.get("episodeCount"),
                        "status": anime.get("status") or "N/A",
                        "description": anime.get("synopsis"),
                        "coverImage": {
                            "large": anime.get("posterImage", {}).get("original")
                        }
                    }
        except Exception as e:
            await rep.report(f"Kitsu Fallback Error: {e}", "error")
            return {}

    @handle_logs
    async def get_jikan_data(self):
        jikan_api = f"https://api.jikan.moe/v4/anime?q={self.__ani_name}&limit=1"
        try:
            async with ClientSession() as sess:
                async with sess.get(jikan_api, timeout=10) as resp:
                    if resp.status != 200:
                        return {}
                    data = await resp.json()
                    if not data.get("data"):
                        return {}
                    anime = data["data"][0]
                    return {
                        "title": {
                            "romaji": anime.get("title"),
                            "english": anime.get("title_english"),
                            "native": anime.get("title_japanese")
                        },
                        "genres": [g["name"] for g in anime.get("genres", [])],
                        "episodes": anime.get("episodes"),
                        "status": anime.get("status"),
                        "description": anime.get("synopsis"),
                        "coverImage": {"large": anime.get("images", {}).get("jpg", {}).get("large_image_url")},
                        "startDate": {
                            "year": anime.get("aired", {}).get("from", "").split("-")[0] if anime.get("aired", {}).get("from") else None,
                            "month": anime.get("aired", {}).get("from", "").split("-")[1] if anime.get("aired", {}).get("from") else None,
                            "day": anime.get("aired", {}).get("from", "").split("-")[2][:2] if anime.get("aired", {}).get("from") else None
                        },
                        "averageScore": anime.get("score", None)
                    }
        except Exception as e:
            await rep.report(f"Jikan Fallback Error: {e}", "error")
            return {}

    @handle_logs
    async def get_ann_data(self):
        ann_api = f"https://www.animenewsnetwork.com/encyclopedia/reports.xml?id=155&type=anime&name={self.__ani_name}"
        try:
            async with ClientSession() as sess:
                async with sess.get(ann_api, timeout=10) as resp:
                    if resp.status != 200:
                        return {}
                    xml_data = await resp.text()
                    root = ET.fromstring(xml_data)
                    anime_data = {}
                    for item in root.findall(".//item"):
                        title = item.find("title").text
                        if self.__ani_name.lower() in title.lower():
                            release_date = item.find("release_date").text if item.find("release_date") else None
                            start_date = {}
                            if release_date:
                                try:
                                    start_year, start_month, start_day = map(int, release_date.split("-"))
                                    start_date = {"year": start_year, "month": start_month, "day": start_day}
                                except:
                                    pass
                            anime_data = {
                                "title": {"romaji": title},
                                "description": item.find("description").text or "N/A",
                                "genres": item.find("genres").text.split(", ") if item.find("genres") else [],
                                "coverImage": {"large": item.find("image").text} if item.find("image") else {},
                                "startDate": start_date
                            }
                            break
                    return anime_data
        except Exception as e:
            await rep.report(f"ANN Fallback Error: {e}", "error")
            return {}

    @handle_logs
    async def get_season(self, anime_data: dict, parsed_data: dict = None) -> str:
        """Detect the anime season number from parsed filename or API data."""
        # Try to get season from parsed filename (anitopy data)
        if parsed_data and parsed_data.get("anime_season"):
            anime_season = parsed_data.get("anime_season")
            # Handle case where anime_season is a list (e.g., ['2'] or ['01'])
            if isinstance(anime_season, list):
                anime_season = anime_season[-1] if anime_season else "1"
            try:
                season_num = int(anime_season)
                return f"Season {season_num}"
            except (ValueError, TypeError):
                pass  # Fallback to other methods if conversion fails

            # Fallback to API data (e.g., AniList or Jikan)
            if anime_data.get("season") and anime_data.get("seasonYear"):
                # AniList sometimes includes season info indirectly; try to infer from title or synonyms
                titles = anime_data.get("title", {})
                synonyms = anime_data.get("synonyms", [])
                all_titles = [titles.get(k) for k in ("romaji", "english", "native") if titles.get(k)] + synonyms
                for title in all_titles:
                    # Look for patterns like "Season 2", "2nd Season", or "S2" in titles/synonyms
                    title_lower = title.lower()
                    if "season" in title_lower or "s" in title_lower:
                        import re
                        match = re.search(r"(?:season|s)\s*(\d+)", title_lower, re.IGNORECASE)
                        if match:
                            return f"Season {match.group(1)}"

            # Fallback to default if no season info is found
            return "Season 1"  # Assume first season if no data is available

    @handle_logs
    async def get_anidata(self):
        res_code, resp_json, res_heads = await self.post_data()
        while res_code == 404 and self.__ani_year > 2020:
            self.__update_vars()
            await rep.report(f"AniList Query Name: {self.__ani_name}, Retrying with {self.__ani_year}", "warning", log=False)
            res_code, resp_json, res_heads = await self.post_data()

        if res_code == 404:
            self.__update_vars(year=False)
            res_code, resp_json, res_heads = await self.post_data()

        if res_code == 200:
            return resp_json.get('data', {}).get('Media', {}) or {}
        elif res_code == 429:
            f_timer = int(res_heads['Retry-After'])
            await rep.report(f"AniList API FloodWait: {res_code}, Sleeping for {f_timer} !!", "error")
            await asleep(f_timer)
            return await self.get_anidata()
        elif res_code in [500, 501, 502]:
            await rep.report(f"AniList Server API Error: {res_code}, Waiting 5s to Try Again !!", "error")
            await asleep(5)
            return await self.get_anidata()
        else:
            await rep.report(f"AniList API Error: {res_code}, trying Jikan fallback...", "warning", log=False)
            jikan_data = await self.get_jikan_data()
            if jikan_data:
                return jikan_data
            await rep.report(f"Jikan API failed, trying ANN fallback...", "warning", log=False)
            ann_data = await self.get_ann_data()
            if ann_data:
                return ann_data
            await rep.report(f"ANN API failed, trying Kitsu fallback...", "warning", log=False)
            kitsu_data = await self.get_kitsu_data()
            return kitsu_data

class TextEditor:
    def __init__(self, name):
        self.__name = name
        self.adata = {}
        self.pdata = parse(name)

    async def load_anilist(self):
        cache_names = []
        for option in [(False, False), (False, True), (True, False), (True, True)]:
            ani_name = await self.parse_name(*option)
            if ani_name in cache_names:
                continue
            cache_names.append(ani_name)
            self.adata = await AniLister(ani_name, datetime.now().year).get_anidata()
            if self.adata:
                break

    @handle_logs
    async def get_id(self):
        if (ani_id := self.adata.get('id')) and str(ani_id).isdigit():
            return ani_id

    @handle_logs
    async def parse_name(self, no_s=False, no_y=False):
        anime_name = self.pdata.get("anime_title")
        anime_season = self.pdata.get("anime_season")
        anime_year = self.pdata.get("anime_year")
        if anime_name:
            pname = anime_name
            if not no_s and self.pdata.get("episode_number") and anime_season:
                pname += f" {anime_season}"
            if not no_y and anime_year:
                pname += f" {anime_year}"
            return pname
        return anime_name

    @handle_logs
    async def get_poster(self):
        if anime_id := await self.get_id():
            return f"https://img.anili.st/media/{anime_id}"
        kitsu_data = await AniLister(self.__name, datetime.now().year).get_kitsu_data()
        if kitsu_data and (poster := kitsu_data.get("coverImage", {}).get("large")):
            return poster
        jikan_data = await AniLister(self.__name, datetime.now().year).get_jikan_data()
        if jikan_data and (poster := jikan_data.get("coverImage", {}).get("large")):
            return poster
        try:
            async with ClientSession() as sess:
                async with sess.get("https://api.waifu.pics/sfw/waifu") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("url", "https://telegra.ph/file/112ec08e59e73b6189a20.jpg")
        except Exception as e:
            await rep.report(f"Waifu.pics Fallback Error: {e}", "error")
        return "https://telegra.ph/file/112ec08e59e73b6189a20.jpg"

    @handle_logs
    async def get_upname(self, qual=""):
        anime_name = self.pdata.get("anime_title")
        codec = 'HEVC' if 'libx265' in ffargs[qual] else 'AV1' if 'libaom-av1' in ffargs[qual] else ''
        lang = 'Multi-Audio' if 'multi-audio' in self.__name.lower() else 'Sub'
        anime_season = str(ani_s[-1]) if (ani_s := self.pdata.get('anime_season', '01')) and isinstance(ani_s, list) else str(ani_s)
        if anime_name and self.pdata.get("episode_number"):
            titles = self.adata.get('title', {})
            return f"""[S{anime_season}-{'E'+str(self.pdata.get('episode_number')) if self.pdata.get('episode_number') else ''}] {titles.get('english') or titles.get('romaji') or titles.get('native')} {'['+qual+'p]' if qual else ''} {'['+codec.upper()+'] ' if codec else ''}{'['+lang+']'} {Var.BRAND_UNAME}.mkv"""

    @handle_logs
async def get_caption(self):
    sd = self.adata.get('startDate', {})
    # Convert month to integer and validate all fields before accessing month_name
    startdate = (f"{month_name[int(sd['month'])]} {sd['day']}, {sd['year']}" 
                 if sd.get('day') and sd.get('month') and sd.get('year') 
                 and str(sd['month']).isdigit() else "")
    ed = self.adata.get('endDate', {})
    enddate = (f"{month_name[int(ed['month'])]} {ed['day']}, {ed['year']}" 
               if ed.get('day') and ed.get('month') and ed.get('year') 
               and str(ed['month']).isdigit() else "")
    titles = self.adata.get("title", {})
    # Get season number using AniLister's get_season method, passing parsed_data
    lister = AniLister(self.__name, datetime.now().year)
    season = await lister.get_season(self.adata, parsed_data=self.pdata)

    return CAPTION_FORMAT.format(
        title=titles.get('english') or titles.get('romaji') or titles.get('native'),
        form=self.adata.get("format") or "N/A",
        genres=", ".join(f"{GENRES_EMOJI[x]} #{x.replace(' ', '_').replace('-', '_')}" for x in (self.adata.get('genres') or [])),
        season=season,
        avg_score=f"{sc}%" if (sc := self.adata.get('averageScore')) else "N/A",
        status=self.adata.get("status") or "N/A",
        start_date=startdate or "N/A",
        end_date=enddate or "N/A",
        t_eps=self.adata.get("episodes") or "N/A",
        plot=(desc if (desc := self.adata.get("description") or "N/A") and len(desc) < 200 else desc[:200] + "..."),
        ep_no=self.pdata.get("episode_number"),
        cred=Var.BRAND_UNAME,
    )