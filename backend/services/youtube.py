import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from database import db_session
from services.youtube_cookies import temporary_cookie_file
from services.youtube_setup import friendly_error, runtime_options


YOUTUBE_HOSTS = {"youtube.com", "youtu.be", "music.youtube.com", "youtubekids.com"}
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def _host(value: str) -> str:
    return (urlsplit(value).hostname or "").lower().removeprefix("www.")


def is_youtube_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        host = _host(value)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return False
        if parsed.port not in {None, 80, 443}:
            return False
        return any(host == domain or host.endswith(f".{domain}") for domain in YOUTUBE_HOSTS)
    except (ValueError, UnicodeError):
        return False


def youtube_video_id(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if host == "youtu.be":
            candidate = parsed.path.strip("/").split("/", 1)[0]
        elif parsed.path.startswith("/shorts/") or parsed.path.startswith("/embed/"):
            candidate = parsed.path.strip("/").split("/", 2)[1]
        else:
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        return candidate if VIDEO_ID_RE.fullmatch(candidate or "") else ""
    except (ValueError, IndexError):
        return ""


def canonical_video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def without_playlist(value: str) -> str:
    parsed = urlsplit(value)
    query = parse_qs(parsed.query)
    query.pop("list", None)
    query.pop("index", None)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), ""))


def is_channel_url(value: str) -> bool:
    try:
        path = urlsplit(value).path.rstrip("/")
        return bool(re.match(r"^/(?:@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)$", path))
    except ValueError:
        return False


def analysis_targets(
    url: str,
    content_filter: str,
    expand_playlist: bool,
) -> tuple[list[tuple[str, str]], str, bool]:
    video_id = youtube_video_id(url)
    parsed = urlsplit(url)
    playlist_requested = expand_playlist and bool(parse_qs(parsed.query).get("list") or parsed.path == "/playlist")
    if video_id and not playlist_requested:
        return [(without_playlist(url), "video")], "video", True
    if is_channel_url(url):
        base = url.rstrip("/")
        targets = []
        if content_filter in ("videos", "both"):
            targets.append((f"{base}/videos", "video"))
        if content_filter in ("shorts", "both"):
            targets.append((f"{base}/shorts", "short"))
        return targets, "channel", False
    source_type = "playlist" if playlist_requested else "video"
    return [(url, "playlist")], source_type, False


@dataclass
class Analysis:
    id: str
    username: str
    url: str
    content_filter: str
    expand_playlist: bool
    status: str = "pending"
    progress: int = 0
    title: str = "YouTube"
    source_type: str = "video"
    items: list[dict] = field(default_factory=list)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    task: asyncio.Task | None = None

    def public(self) -> dict:
        return {
            "analysis_id": self.id,
            "status": self.status,
            "progress": self.progress,
            "title": self.title,
            "source_type": self.source_type,
            "items": self.items if self.status == "complete" else [],
            "count": len(self.items),
            "error": self.error,
            "limit": 500,
        }


class YouTubeAnalysisService:
    def __init__(self):
        self._analyses: dict[str, Analysis] = {}

    def _cleanup(self):
        cutoff = time.time() - 30 * 60
        for analysis_id, analysis in list(self._analyses.items()):
            if analysis.created_at < cutoff and not (analysis.task and not analysis.task.done()):
                self._analyses.pop(analysis_id, None)

    async def create(self, username: str, url: str, content_filter: str, expand_playlist: bool) -> dict:
        if not is_youtube_url(url):
            raise ValueError("Only YouTube URLs can be analyzed")
        self._cleanup()
        if any(a.username == username and a.task and not a.task.done() for a in self._analyses.values()):
            raise RuntimeError("A YouTube analysis is already running")
        analysis = Analysis(str(uuid.uuid4()), username, url.strip(), content_filter, expand_playlist)
        self._analyses[analysis.id] = analysis
        analysis.task = asyncio.create_task(self._run(analysis))
        return analysis.public()

    def get(self, analysis_id: str, username: str) -> dict:
        self._cleanup()
        analysis = self._analyses.get(analysis_id)
        if not analysis or analysis.username != username:
            raise KeyError(analysis_id)
        return analysis.public()

    def raw(self, analysis_id: str, username: str) -> Analysis:
        analysis = self._analyses.get(analysis_id)
        if not analysis or analysis.username != username:
            raise KeyError(analysis_id)
        if analysis.status != "complete":
            raise RuntimeError("YouTube analysis is not complete")
        return analysis

    async def cancel(self, analysis_id: str, username: str):
        analysis = self.raw_or_none(analysis_id, username)
        if not analysis:
            raise KeyError(analysis_id)
        if analysis.task and not analysis.task.done():
            analysis.task.cancel()
        self._analyses.pop(analysis_id, None)

    def raw_or_none(self, analysis_id: str, username: str) -> Analysis | None:
        analysis = self._analyses.get(analysis_id)
        return analysis if analysis and analysis.username == username else None

    async def _run(self, analysis: Analysis):
        analysis.status = "running"
        analysis.progress = 5
        try:
            extracted = await asyncio.wait_for(
                asyncio.to_thread(self._extract, analysis.url, analysis.content_filter, analysis.expand_playlist),
                timeout=180,
            )
            analysis.progress = 75
            keys = [f"youtube:{item['id']}" for item in extracted["items"]]
            duplicates: set[str] = set()
            if keys:
                placeholders = ",".join("?" for _ in keys)
                async with db_session() as db:
                    active = await (await db.execute(
                        f"SELECT source_key FROM downloads WHERE source_key IN ({placeholders})", keys  # nosec B608
                    )).fetchall()
                    history = await (await db.execute(
                        f"SELECT source_key FROM history WHERE status = 'complete' AND source_key IN ({placeholders})", keys  # nosec B608
                    )).fetchall()
                duplicates = {row[0] for row in active + history}
            for item in extracted["items"]:
                item["duplicate"] = f"youtube:{item['id']}" in duplicates
                item["selected"] = not item["duplicate"]
            analysis.title = extracted["title"]
            analysis.source_type = extracted["source_type"]
            analysis.items = extracted["items"]
            analysis.progress = 100
            analysis.status = "complete"
        except asyncio.CancelledError:
            analysis.status = "cancelled"
            raise
        except Exception as exc:
            analysis.status = "error"
            analysis.error = friendly_error(str(exc))[:300]

    @staticmethod
    def _extract(url: str, content_filter: str, expand_playlist: bool) -> dict:
        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError("yt-dlp is not installed") from exc

        targets, source_type, single_video = analysis_targets(url, content_filter, expand_playlist)

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "format": "all",
            "extract_flat": True,
            "playlistend": 501,
            "ignoreerrors": not single_video,
            "lazy_playlist": False,
            **runtime_options(),
        }
        items = []
        seen = set()
        title = "YouTube"
        with temporary_cookie_file() as cookie_file:
            if cookie_file:
                options["cookiefile"] = cookie_file
            with yt_dlp.YoutubeDL(options) as ydl:
                for target, kind in targets:
                    info = ydl.extract_info(target, download=False)
                    if not info:
                        continue
                    title = info.get("title") or info.get("channel") or title
                    entries = info.get("entries") or [info]
                    for entry in entries:
                        if not entry or entry.get("live_status") in {"is_live", "is_upcoming"}:
                            continue
                        video_id = str(entry.get("id") or youtube_video_id(entry.get("url", "")))
                        if not VIDEO_ID_RE.fullmatch(video_id) or video_id in seen:
                            continue
                        seen.add(video_id)
                        items.append({
                            "id": video_id,
                            "url": canonical_video_url(video_id),
                            "title": str(entry.get("title") or video_id)[:300],
                            "channel": str(entry.get("channel") or entry.get("uploader") or "")[:160],
                            "duration": int(entry.get("duration") or 0),
                            "thumbnail": str(entry.get("thumbnail") or ""),
                            "kind": "short" if kind == "short" else "video",
                        })
                        if len(items) >= 500:
                            break
                    if len(items) >= 500:
                        break
        if not items:
            raise RuntimeError("No public downloadable videos were found")
        return {"title": str(title)[:160], "source_type": source_type, "items": items}


youtube_analyses = YouTubeAnalysisService()
