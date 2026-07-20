from database import db_session


async def load_queue_revision() -> int:
    async with db_session() as db:
        row = await (await db.execute(
            "SELECT revision FROM queue_revision WHERE id = 1"
        )).fetchone()
        return int(row[0]) if row else 0


async def load_queue_snapshot() -> dict:
    """Read the complete queue view without holding the connection afterwards."""
    async with db_session(row_factory=True) as db:
        await db.execute("BEGIN")
        revision_row = await (await db.execute(
            "SELECT revision FROM queue_revision WHERE id = 1"
        )).fetchone()
        active = [dict(row) for row in await (
            await db.execute(
                "SELECT * FROM downloads WHERE status NOT IN ('complete', 'failed') "
                "ORDER BY position ASC, created_at ASC"
            )
        ).fetchall()]
        finished = [dict(row) for row in await (
            await db.execute(
                "SELECT * FROM downloads WHERE status IN ('complete', 'failed') "
                "ORDER BY updated_at DESC"
            )
        ).fetchall()]
        packages = [dict(row) for row in await (
            await db.execute("SELECT * FROM packages ORDER BY created_at DESC")
        ).fetchall()]
        torrents = [dict(row) for row in await (
            await db.execute("SELECT * FROM torrents ORDER BY created_at DESC")
        ).fetchall()]

    downloads = active + finished
    by_package: dict[str, list[dict]] = {}
    for download in downloads:
        package_id = download.get("package_id")
        if package_id:
            by_package.setdefault(package_id, []).append(download)

    for package in packages:
        members = by_package.get(package["id"], [])
        package["downloads"] = members
        package["total_files"] = len(members)
        package["completed_files"] = sum(
            item["status"] == "complete" for item in members
        )
        package["active_files"] = sum(
            item["status"] == "downloading" for item in members
        )
        package["total_size"] = sum(item.get("size") or 0 for item in members)
        package["total_downloaded"] = sum(
            item.get("downloaded") or 0 for item in members
        )
        package["progress"] = (
            round(package["total_downloaded"] / package["total_size"] * 100, 1)
            if package["total_size"] > 0 else 0
        )

    return {
        "db_revision": int(revision_row[0]) if revision_row else 0,
        "downloads": downloads,
        "packages": packages,
        "torrents": torrents,
    }
