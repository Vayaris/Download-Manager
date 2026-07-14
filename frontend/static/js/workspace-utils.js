(function(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.DownloadWorkspaceUtils = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function() {
  "use strict";

  function number(value) {
    const parsed = Number(value || 0);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function normalizePath(value) {
    const path = String(value || "").trim().replace(/\/+$/, "");
    return path || "/";
  }

  function isPathInside(path, root) {
    const normalizedPath = normalizePath(path);
    const normalizedRoot = normalizePath(root);
    return normalizedRoot === "/"
      || normalizedPath === normalizedRoot
      || normalizedPath.startsWith(normalizedRoot + "/");
  }

  function storageForDestination(destination, storage) {
    return (storage || [])
      .filter(item => item && item.path && isPathInside(destination, item.path))
      .sort((a, b) => normalizePath(b.path).length - normalizePath(a.path).length)[0] || null;
  }

  function summarizeStorage(storage) {
    const entries = Array.isArray(storage) ? storage : [];
    const available = entries.filter(item => item && item.available);
    const total = available.reduce((sum, item) => sum + number(item.total), 0);
    const used = available.reduce((sum, item) => sum + number(item.used), 0);
    const free = available.reduce((sum, item) => sum + number(item.free), 0);
    return {
      count: entries.length,
      availableCount: available.length,
      unavailableCount: entries.length - available.length,
      total,
      used,
      free,
      percent: total > 0 ? Math.round((used / total) * 1000) / 10 : null,
    };
  }

  function isValidPasteToken(value) {
    const token = String(value || "").trim();
    if (/^magnet:\?/i.test(token)) {
      try {
        return new URLSearchParams(token.slice(token.indexOf("?") + 1)).has("xt");
      } catch {
        return false;
      }
    }
    try {
      const url = new URL(token);
      return ["http:", "https:", "ftp:"].includes(url.protocol) && Boolean(url.hostname);
    } catch {
      return false;
    }
  }

  function parseGlobalPasteLinks(text) {
    const tokens = String(text || "").trim().split(/\s+/).filter(Boolean);
    return tokens.length && tokens.every(isValidPasteToken) ? tokens : [];
  }

  function medianPositive(values) {
    const sorted = (values || []).map(number).filter(value => value > 0).sort((a, b) => a - b);
    if (!sorted.length) return 0;
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function isActive(item) {
    return item && !["complete", "failed"].includes(item.status);
  }

  function computeQueueMetrics(downloads, torrents) {
    const activeDownloads = (downloads || []).filter(isActive);
    const activeTorrents = (torrents || []).filter(isActive);
    let remaining = 0;
    let known = 0;
    let blocked = 0;
    for (const item of activeDownloads) {
      const size = number(item.size);
      if (size > 0) {
        known++;
        remaining += Math.max(0, size - number(item.downloaded));
      }
      if (["paused", "error", "duplicate_pending"].includes(item.status)) blocked++;
    }
    blocked += activeTorrents.filter(item => ["error", "import_failed"].includes(item.status)).length;
    return {
      total: activeDownloads.length + activeTorrents.length,
      known,
      unknown: activeDownloads.length + activeTorrents.length - known,
      remaining,
      blocked,
    };
  }

  function computeStoragePressure(storage, downloads, torrents) {
    const entries = (storage || []).map(item => ({
      path: item.path,
      required: 0,
      unknown: 0,
      free: number(item.free),
      available: Boolean(item.available),
      state: "ok",
      ratio: 0,
    }));
    const byPath = new Map(entries.map(item => [normalizePath(item.path), item]));

    function targetFor(item) {
      const match = storageForDestination(item.destination, storage);
      return match ? byPath.get(normalizePath(match.path)) : null;
    }

    for (const item of (downloads || []).filter(isActive)) {
      const target = targetFor(item);
      if (!target) continue;
      const size = number(item.size);
      if (size > 0) target.required += Math.max(0, size - number(item.downloaded));
      else target.unknown++;
    }
    for (const item of (torrents || []).filter(isActive)) {
      const target = targetFor(item);
      if (!target) continue;
      const size = number(item.size);
      if (size > 0) target.required += size;
      else target.unknown++;
    }

    for (const item of entries) {
      if (!item.available || item.required <= 0) continue;
      item.ratio = item.free > 0 ? item.required / item.free : Infinity;
      item.state = item.ratio > 1 ? "critical" : item.ratio >= 0.9 ? "warning" : "ok";
    }
    return entries;
  }

  return {
    computeQueueMetrics,
    computeStoragePressure,
    isPathInside,
    isValidPasteToken,
    medianPositive,
    normalizePath,
    parseGlobalPasteLinks,
    storageForDestination,
    summarizeStorage,
  };
});
