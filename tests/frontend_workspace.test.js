const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const utils = require("../frontend/static/js/workspace-utils.js");

test("storage units follow the selected interface language", () => {
  let language = "fr";
  const context = {
    getLang: () => language,
    fetch: () => {},
  };
  vm.runInNewContext(
    fs.readFileSync("frontend/static/js/api.js", "utf8"),
    context,
  );
  assert.equal(context.formatSize(1024 ** 3), "1.0 Go");
  assert.equal(context.formatSize(1024 ** 4), "1.0 To");
  language = "en";
  assert.equal(context.formatSize(1024 ** 3), "1.0 GB");
  assert.equal(context.formatSize(1024 ** 4), "1.0 TB");
});

test("global paste accepts links and magnets but leaves ordinary text alone", () => {
  assert.deepEqual(
    utils.parseGlobalPasteLinks("https://example.com/file\nmagnet:?xt=urn:btih:abc123"),
    ["https://example.com/file", "magnet:?xt=urn:btih:abc123"],
  );
  assert.deepEqual(utils.parseGlobalPasteLinks("look at https://example.com/file"), []);
  assert.deepEqual(utils.parseGlobalPasteLinks("magnet:?dn=missing-hash"), []);
});

test("storage summary uses weighted capacity and excludes unavailable totals", () => {
  const summary = utils.summarizeStorage([
    { available: true, total: 1000, used: 500, free: 500 },
    { available: true, total: 3000, used: 2400, free: 600 },
    { available: false, total: 9000, used: 9000, free: 0 },
  ]);
  assert.deepEqual(summary, {
    count: 3,
    availableCount: 2,
    unavailableCount: 1,
    total: 4000,
    used: 2900,
    free: 1100,
    percent: 72.5,
  });
});

test("destination matching respects path boundaries and chooses the deepest root", () => {
  const storage = [{ path: "/mnt/media" }, { path: "/mnt/media/movies" }];
  assert.equal(utils.storageForDestination("/mnt/media/movies/4k", storage).path, "/mnt/media/movies");
  assert.equal(utils.storageForDestination("/mnt/media2/file", storage), null);
});

test("queue metrics keep AllDebrid torrents unknown", () => {
  const metrics = utils.computeQueueMetrics(
    [
      { status: "downloading", size: 1000, downloaded: 250 },
      { status: "pending", size: 0, downloaded: 0 },
      { status: "paused", size: 500, downloaded: 100 },
    ],
    [{ status: "processing", size: 2000, downloaded: 800 }],
  );
  assert.deepEqual(metrics, {
    total: 4,
    known: 2,
    unknown: 2,
    remaining: 1150,
    blocked: 1,
  });
  assert.equal(utils.medianPositive([100, 800, 300, 0]), 300);
});

test("storage pressure warns at 90 percent and becomes critical above free space", () => {
  const storage = [{ path: "/mnt/media", free: 1000, available: true }];
  const warning = utils.computeStoragePressure(
    storage,
    [{ destination: "/mnt/media/films", status: "downloading", size: 1000, downloaded: 200 }],
    [{ destination: "/mnt/media/films", status: "processing", size: 100 }],
  )[0];
  assert.equal(warning.required, 900);
  assert.equal(warning.state, "warning");

  const critical = utils.computeStoragePressure(
    storage,
    [{ destination: "/mnt/media", status: "pending", size: 1001, downloaded: 0 }],
    [],
  )[0];
  assert.equal(critical.state, "critical");
});

test("late duplicate dialog can apply one explicit action to displayed conflicts", () => {
  const app = fs.readFileSync("frontend/static/js/app.js", "utf8");
  assert.match(app, /id="duplicate-always-apply"/);
  assert.match(app, /\/api\/downloads\/conflicts\/resolve/);
  assert.match(app, /conflict_ids: applyToAll \? conflicts\.map/);
});

test("settings expose an explicit existing-file protection switch", () => {
  const html = fs.readFileSync("frontend/settings.html", "utf8");
  const settings = fs.readFileSync("frontend/static/js/settings.js", "utf8");
  assert.match(html, /id="existing-file-check-enabled" checked/);
  assert.match(settings, /existing_file_check_enabled: existingFileCheck/);
  assert.match(settings, /settings_existing_file_check_confirm/);
});
