"""Temporary aria2 bandwidth reserve. Configured limits are never rewritten."""
import asyncio
import time

from config import get_config
from services.aria2_service import aria2


class InterfacePriority:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.pending = 0
        self.factor = 100
        self.recovery_at = None
        self.configuration = None
        self.applied_target = None
        self.checked_at = None
        self.lock = asyncio.Lock()

    def begin(self):
        self.pending += 1
        self.recovery_at = None

    def end(self):
        self.pending = max(0, self.pending - 1)
        if not self.pending:
            self.recovery_at = self.clock() + 5

    def snapshot(self):
        cfg = get_config()["downloads"]
        cap = max(0, int(cfg.get("speed_limit", 0) or 0))
        enabled = bool(cfg.get("priority_interface_enabled", False))
        configuration = (cap, enabled)
        if configuration != self.configuration:
            self.factor = 100
            self.configuration = configuration
        if not enabled or not cap:
            self.factor = 100
        elif self.pending:
            self.factor = 80
        elif self.factor < 100 and self.recovery_at is not None:
            now = self.clock()
            if now >= self.recovery_at:
                steps = int((now - self.recovery_at) // 5) + 1
                self.factor = min(100, self.factor + steps * 5)
                self.recovery_at += steps * 5
        target = cap * 1024 * 1024 * self.factor // 100
        return {
            "configured_mb_s": cap, "configured_mib_s": cap,
            "priority_interface_enabled": enabled,
            "priority_interface_active": enabled and cap > 0 and self.factor < 100,
            "temporary_limit_bytes_s": target,
            "effective_percent": self.factor,
            "pending_explorations": self.pending,
        }

    async def apply(self, force=False):
        async with self.lock:
            state = self.snapshot()
            target = state["temporary_limit_bytes_s"]
            now = self.clock()
            try:
                changed = force or target != self.applied_target
                if not changed and (self.checked_at is None or now - self.checked_at >= 5):
                    options = await asyncio.wait_for(aria2.get_global_option(), timeout=2)
                    changed = int(options.get("max-overall-download-limit", 0) or 0) != target
                    self.checked_at = now
                if changed:
                    await asyncio.wait_for(aria2.change_global_option({
                        "max-overall-download-limit": str(target)
                    }), timeout=2)
                    self.applied_target = target
                    self.checked_at = now
            except Exception:
                self.applied_target = None
                raise
            return state


interface_priority = InterfacePriority()
