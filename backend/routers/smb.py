"""SMB/CIFS share management router."""
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from auth import get_current_user
from config import get_config, save_config
from services.smb import mount_share, unmount_share, is_mounted

router = APIRouter()

_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')


class SmbShareIn(BaseModel):
    name: str
    host: str
    share: str
    username: Optional[str] = ""
    password: Optional[str] = ""
    domain: Optional[str] = ""
    vers: Optional[str] = ""       # SMB version: "", "1.0", "2.0", "2.1", "3.0", "3.1.1"
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

    cfg = get_config()
    shares = cfg.get("smb_shares", [])

    if any(s["name"] == name for s in shares):
        raise HTTPException(status_code=400, detail="A share with this name already exists")

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
    shares.append(new_share)
    cfg["smb_shares"] = shares
    save_config(cfg)
    return _share_view(new_share)


@router.delete("/{name}")
async def delete_share(name: str, _=Depends(get_current_user)):
    cfg = get_config()
    shares = cfg.get("smb_shares", [])
    for i, s in enumerate(shares):
        if s["name"] == name:
            unmount_share(s.get("mount_point", ""))
            shares.pop(i)
            cfg["smb_shares"] = shares
            save_config(cfg)
            return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Share not found")


@router.put("/{name}")
async def update_share(name: str, body: SmbShareIn, _=Depends(get_current_user)):
    cfg = get_config()
    shares = cfg.get("smb_shares", [])
    for i, s in enumerate(shares):
        if s["name"] == name:
            new_name = body.name.strip()
            if not _NAME_RE.match(new_name):
                raise HTTPException(status_code=400, detail="Name must contain only letters, numbers, underscores and dashes")
            # Unmount old mount point if name changes
            if new_name != name:
                unmount_share(s.get("mount_point", ""))
            new_share = {
                "name": new_name,
                "host": body.host.strip(),
                "share": body.share.strip(),
                "username": (body.username or "").strip(),
                "password": (body.password or "").strip() or s.get("password", ""),
                "domain": (body.domain or "").strip(),
                "vers": (body.vers or "").strip(),
                "mount_point": _mount_point_for(new_name),
                "auto_mount": body.auto_mount,
            }
            shares[i] = new_share
            cfg["smb_shares"] = shares
            save_config(cfg)
            return _share_view(new_share)
    raise HTTPException(status_code=404, detail="Share not found")


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
