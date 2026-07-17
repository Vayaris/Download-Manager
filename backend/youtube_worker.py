#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from services.youtube_cookies import temporary_cookie_file
from services.youtube_setup import friendly_error, runtime_options


def emit(event: str, **payload):
    print("DMYT " + json.dumps({"event": event, **payload}, ensure_ascii=True), flush=True)


class QuietLogger:
    def debug(self, _message):
        pass

    def warning(self, message):
        print(str(message)[:500], file=sys.stderr, flush=True)

    def error(self, message):
        print(str(message)[:500], file=sys.stderr, flush=True)


def _audio_description(fmt: dict) -> bool:
    text = " ".join(str(fmt.get(key) or "") for key in ("format_note", "format", "name")).lower()
    markers = ("audio description", "description audio", "audio-described", "descriptive", "audiodescription")
    return any(marker in text for marker in markers)


def _quality(fmt: dict) -> tuple:
    return (
        float(fmt.get("quality") or -1),
        float(fmt.get("height") or 0),
        float(fmt.get("fps") or 0),
        float(fmt.get("tbr") or fmt.get("abr") or 0),
        int(fmt.get("filesize") or fmt.get("filesize_approx") or 0),
    )


def rich_format(info: dict) -> tuple[str, list[str]]:
    formats = [fmt for fmt in info.get("formats", []) if fmt.get("format_id")]
    video_only = [fmt for fmt in formats if fmt.get("vcodec") != "none" and fmt.get("acodec") == "none"]
    video_any = [fmt for fmt in formats if fmt.get("vcodec") != "none"]
    if not video_only and not video_any:
        raise RuntimeError("No video stream is available")
    video = max(video_only or video_any, key=_quality)

    audio_by_language = {}
    for fmt in formats:
        if fmt.get("vcodec") != "none" or fmt.get("acodec") in (None, "none") or _audio_description(fmt):
            continue
        language = str(fmt.get("language") or "und").lower().split("-", 1)[0]
        current = audio_by_language.get(language)
        if current is None or _quality(fmt) > _quality(current):
            audio_by_language[language] = fmt
    audios = sorted(
        audio_by_language.values(),
        key=lambda fmt: (-(float(fmt.get("language_preference") or 0)), str(fmt.get("language") or "und")),
    )
    ids = [str(video["format_id"])] + [str(fmt["format_id"]) for fmt in audios]

    manual = set((info.get("subtitles") or {}).keys())
    automatic = {
        language for language in (info.get("automatic_captions") or {})
        if language.lower() in {"fr", "fr-fr", "en", "en-us", "en-gb"}
    }
    return "+".join(ids), sorted(manual | automatic)


MP4_FORMATS = (
    "bv[ext=mp4][vcodec^=avc]+ba[ext=m4a]/b[ext=mp4]",
    "bv[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv+ba/b",
)


def download_mp4(yt_dlp, options: dict, url: str):
    last_error = None
    for index, selector in enumerate(MP4_FORMATS):
        try:
            with yt_dlp.YoutubeDL({**options, "format": selector}) as ydl:
                result = ydl.extract_info(url, download=True)
                return result, ydl.prepare_filename(result)
        except Exception as exc:
            last_error = exc
            if index + 1 >= len(MP4_FORMATS) or "requested format is not available" not in str(exc).lower():
                raise
    raise last_error or RuntimeError("No compatible YouTube format is available")


def download_rich(yt_dlp, options: dict, url: str):
    with yt_dlp.YoutubeDL({**options, "skip_download": True}) as probe:
        info = probe.extract_info(url, download=False)
    selector, subtitles = rich_format(info)
    rich_options = {
        **options,
        "format": selector,
        "allow_multiple_audio_streams": True,
        "merge_output_format": "mkv",
        "writesubtitles": bool(subtitles),
        "writeautomaticsub": bool(subtitles),
        "subtitleslangs": subtitles,
        "subtitlesformat": "best",
        "embedsubtitles": bool(subtitles),
    }
    with yt_dlp.YoutubeDL(rich_options) as ydl:
        result = ydl.extract_info(url, download=True)
        return result, ydl.prepare_filename(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--profile", choices=("mp4", "mkv_multi"), default="mp4")
    parser.add_argument("--speed-limit", type=int, default=0)
    parser.add_argument("--video-id", required=True)
    args = parser.parse_args()

    destination = Path(args.destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        import yt_dlp
    except ImportError:
        emit("error", message="yt-dlp is not installed")
        return 2

    final_path = {"value": ""}

    def progress(data):
        status = data.get("status")
        if status == "downloading":
            total = int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
            downloaded = int(data.get("downloaded_bytes") or 0)
            emit(
                "progress",
                downloaded=downloaded,
                total=total,
                speed=int(data.get("speed") or 0),
                progress=round(downloaded / total * 100, 2) if total else 0,
            )
        elif status == "finished":
            emit("postprocessing", filename=str(data.get("filename") or ""))

    def postprocessor(data):
        if data.get("status") == "started":
            emit("postprocessing")
        elif data.get("status") == "finished":
            info = data.get("info_dict") or {}
            final_path["value"] = str(info.get("filepath") or info.get("_filename") or final_path["value"])

    common = {
        "quiet": True,
        "no_warnings": True,
        "logger": QuietLogger(),
        "progress_hooks": [progress],
        "postprocessor_hooks": [postprocessor],
        "paths": {"home": str(destination), "temp": str(destination)},
        "outtmpl": {"default": "%(title).180B [%(id)s].%(ext)s"},
        "continuedl": True,
        "overwrites": False,
        "nopart": False,
        "windowsfilenames": False,
        "trim_file_name": 220,
        "ratelimit": args.speed_limit * 1024 * 1024 if args.speed_limit > 0 else None,
        "noplaylist": True,
        "postprocessors": [{"key": "FFmpegMetadata", "add_chapters": True}],
        **runtime_options(),
    }

    try:
        with temporary_cookie_file() as cookie_file:
            if cookie_file:
                common["cookiefile"] = cookie_file
            if args.profile == "mkv_multi":
                result, prepared_filename = download_rich(yt_dlp, common, args.url)
            else:
                result, prepared_filename = download_mp4(
                    yt_dlp, {**common, "merge_output_format": "mp4"}, args.url
                )
            final_path["value"] = str(result.get("filepath") or result.get("_filename") or final_path["value"])
            if final_path["value"]:
                final_path["value"] = str(Path(prepared_filename).with_suffix(
                    ".mkv" if args.profile == "mkv_multi" else ".mp4"
                ))
        path = Path(final_path["value"])
        if not path.is_file():
            candidates = sorted(
                (item for item in destination.iterdir() if f"[{args.video_id}]" in item.name),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            path = next((item for item in candidates if item.is_file() and ".part" not in item.name), path)
        if not path.is_file() or destination not in path.resolve().parents:
            raise RuntimeError("The final YouTube file could not be verified")
        emit("complete", filename=path.name, path=str(path.resolve()), size=path.stat().st_size)
        return 0
    except Exception as exc:
        emit("error", message=friendly_error(str(exc)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
