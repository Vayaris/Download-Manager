from fastapi import APIRouter, Depends, HTTPException, Request

from auth import get_current_user
from config import get_config
from models import YouTubeAnalyzeRequest, YouTubeSubmitRequest
from services.youtube import youtube_analyses
from services.youtube_setup import status as youtube_status
from utils import validate_destination


router = APIRouter()


@router.post("/analyses")
async def create_analysis(body: YouTubeAnalyzeRequest, user=Depends(get_current_user)):
    try:
        return await youtube_analyses.create(
            user["username"], body.url, body.content_filter, body.expand_playlist
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str, user=Depends(get_current_user)):
    try:
        return youtube_analyses.get(analysis_id, user["username"])
    except KeyError:
        raise HTTPException(status_code=404, detail="YouTube analysis not found")


@router.delete("/analyses/{analysis_id}")
async def cancel_analysis(analysis_id: str, user=Depends(get_current_user)):
    try:
        await youtube_analyses.cancel(analysis_id, user["username"])
    except KeyError:
        raise HTTPException(status_code=404, detail="YouTube analysis not found")
    return {"status": "cancelled"}


@router.post("/analyses/{analysis_id}/submit")
async def submit_analysis(
    analysis_id: str,
    body: YouTubeSubmitRequest,
    request: Request,
    user=Depends(get_current_user),
):
    validate_destination(body.destination)
    try:
        analysis = youtube_analyses.raw(analysis_id, user["username"])
    except KeyError:
        raise HTTPException(status_code=404, detail="YouTube analysis not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    by_id = {item["id"]: item for item in analysis.items}
    selected = []
    seen = set()
    for video_id in body.selected_ids:
        if video_id in seen or video_id not in by_id:
            continue
        seen.add(video_id)
        selected.append(by_id[video_id])
    if not selected:
        raise HTTPException(status_code=400, detail="Select at least one video")
    if len(selected) > 500:
        raise HTTPException(status_code=400, detail="A YouTube batch is limited to 500 videos")

    cfg = get_config()
    if body.engine == "alldebrid":
        if not cfg["alldebrid"].get("enabled") or not cfg["alldebrid"].get("api_key"):
            raise HTTPException(status_code=400, detail="AllDebrid is not configured")
    elif not cfg.get("youtube", {}).get("direct_enabled"):
        raise HTTPException(status_code=400, detail="The direct YouTube engine is disabled")
    elif not youtube_status()["ready"]:
        raise HTTPException(status_code=400, detail="The direct YouTube dependencies are not ready")

    qm = request.app.state.queue_manager
    package_id = None
    package_name = body.package_name.strip() or analysis.title or "YouTube"
    if len(selected) > 1:
        package_id = await qm.create_package(
            package_name[:160], body.destination, status="assembling", source_count=len(selected)
        )
    ids = await qm.add_youtube_downloads(
        selected,
        body.destination,
        engine=body.engine,
        output_profile=body.output_profile,
        package_id=package_id,
    )
    if package_id:
        await qm.activate_package(package_id, failed_sources=len(selected) - len(ids))
    return {
        "added": len(ids),
        "ignored": len(selected) - len(ids),
        "package_id": package_id,
        "package_name": package_name[:160] if package_id else None,
        "download_ids": ids,
    }
