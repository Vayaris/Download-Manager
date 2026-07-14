"""SMB/CIFS share management router."""
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from auth import get_current_user
from config import get_config, update_config
from services.smb import mount_share, unmount_share, is_mounted

router = APIRouter()

_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')


class SmbShareIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    host: str = Field(min_length=1, max_length=255)
    share: str = Field(min_length=1, max_length=255)
    username: Optional[str] = Field(default="", max_length=255)
    password: Optional[str] = Field(default="", max_length=1024)
    domain: Optional[str] = Field(default="", max_length=255)
    vers: Optional[str] = Field(default="", max_length=16)
    auto_mount: bool = True


def _mount_point_for(name: str) -> str:
    return f"/mnt/smb/{name}"


def _shares_list():
    return get_config().get("smb_shares", [])


def _find_share(name: str) -> Optional[dict]:
    for s in _shares_list():
        if s["name"] == name:
            return s
    return None


def _share_view(s: dict) -> dict:
    """Return share dict with mounted status; password always stripped."""
    return {
        "name": s["name"],
        "host": s["host"],
        "share": s["share"],
        "username": s.get("username", ""),
        "domain": s.get("domain", ""),
        "vers": s.get("vers", ""),
        "auto_mount": s.get("auto_mount", False),
        "mount_point": s.get("mount_point", ""),
        "mounted": is_mounted(s.get("mount_point", "")),
    }


@router.get("/")
async def list_shares(_=Depends(get_current_user)):
    return [_share_view(s) for s in _shares_list()]


@router.post("/")
async def add_share(body: SmbShareIn, _=Depends(get_current_user)):
    name = body.name.strip()
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Name must contain only letters, numbers, underscores and dashes")

    new_share = {
        "name": name,
        "host": body.host.strip(),
        "share": body.share.strip(),
        "username": (body.username or "").strip(),
        "password": (body.password or "").strip(),
        "domain": (body.domain or "").strip(),
        "vers": (body.vers or "").strip(),
        "mount_point": _mount_point_for(name),
        "auto_mount": body.auto_mount,
    }
    def add(config):
        shares = config.setdefault("smb_shares", [])
        if any(share["name"] == name for share in shares):
            raise HTTPException(status_code=400, detail="A share with this name already exists")
        shares.append(new_share)

    update_config(add)
    return _share_view(new_share)


@router.delete("/{name}")
async def delete_share(name: str, _=Depends(get_current_user)):
    current = _find_share(name)
    if not current:
        raise HTTPException(status_code=404, detail="Share not found")
    unmount_share(current.get("mount_point", ""))

    def remove(config):
        config["smb_shares"] = [share for share in config.get("smb_shares", []) if share["name"] != name]

    update_config(remove)
    return {"status": "deleted"}


@router.put("/{name}")
async def update_share(name: str, body: SmbShareIn, _=Depends(get_current_user)):
    current = _find_share(name)
    if not current:
        raise HTTPException(status_code=404, detail="Share not found")
    new_name = body.name.strip()
    if not _NAME_RE.match(new_name):
        raise HTTPException(status_code=400, detail="Name must contain only letters, numbers, underscores and dashes")
    if new_name != name and _find_share(new_name):
        raise HTTPException(status_code=400, detail="A share with this name already exists")
    if new_name != name:
        unmount_share(current.get("mount_point", ""))
    new_share = {
        "name": new_name,
        "host": body.host.strip(),
        "share": body.share.strip(),
        "username": (body.username or "").strip(),
        "password": (body.password or "").strip() or current.get("password", ""),
        "domain": (body.domain or "").strip(),
        "vers": (body.vers or "").strip(),
        "mount_point": _mount_point_for(new_name),
        "auto_mount": body.auto_mount,
    }

    def replace(config):
        shares = config.setdefault("smb_shares", [])
        if new_name != name and any(share["name"] == new_name for share in shares):
            raise HTTPException(status_code=400, detail="A share with this name already exists")
        for index, share in enumerate(shares):
            if share["name"] == name:
                shares[index] = new_share
                return
        raise HTTPException(status_code=409, detail="Share list changed; reload and retry")

    update_config(replace)
    return _share_view(new_share)


@router.post("/{name}/mount")
async def mount(name: str, _=Depends(get_current_user)):
    share = _find_share(name)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
    ok, msg = mount_share(share)
    return {"success": ok, "message": msg, "mounted": is_mounted(share.get("mount_point", ""))}


@router.post("/{name}/unmount")
async def unmount(name: str, _=Depends(get_current_user)):
    share = _find_share(name)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
    ok, msg = unmount_share(share.get("mount_point", ""))
    return {"success": ok, "message": msg, "mounted": is_mounted(share.get("mount_point", ""))}
