const assert = require("assert");
const fs = require("fs");
const path = require("path");

const fixtures = require("../miniprogram-v2/fixtures");
const response = require("../miniprogram-v2/normalizers/response");
const today = require("../miniprogram-v2/normalizers/today");
const projection = require("../miniprogram-v2/normalizers/projection");
const progress = require("../miniprogram-v2/normalizers/progress");
const report = require("../miniprogram-v2/normalizers/report");
const { parseSseBlock, createDecoder } = require("../miniprogram-v2/services/stream");

function backendFixture(name) {
  const file = path.join(__dirname, "..", "backend", "tests", "fixtures", "contracts", name);
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function frontendFile(name) {
  return fs.readFileSync(path.join(__dirname, "..", "miniprogram-v2", name), "utf8");
}

function run() {
  assert.deepStrictEqual(response.unwrapResponse({ code: 0, data: { ok: true } }), { ok: true });
  assert.deepStrictEqual(response.unwrapResponse({ session_id: "raw-sandbox" }), { session_id: "raw-sandbox" });
  assert.throws(() => response.unwrapResponse({ code: 400, message: "bad" }), /./);

  const normalToday = today.normalizeOverview(fixtures.today.normal);
  assert.strictEqual(normalToday.weather.location, "青岛");
  assert.strictEqual(normalToday.courses[0].periodLabel, "第 1-2 节");
  assert.strictEqual(today.event({ event_type: "course", sort_key: 1, time: "08:00", end_time: "10:00" }).timeLabel, "第 1-2 节");
  assert.strictEqual(today.event({ event_type: "exam", time: "00:00" }).timeLabel, "时间待定");
  assert.strictEqual(today.normalizeOverview(fixtures.today.weatherFailure).weather.available, false);
  assert.strictEqual(today.todayCompletion([], "2026-08-13").available, false);

  const backendProgress = backendFixture("progress.json");
  assert.strictEqual(progress.normalizeProgress(backendProgress.partial).percent, 50);
  assert.strictEqual(progress.normalizeProgress(backendProgress.complete).percent, 100);
  assert.strictEqual(progress.normalizeProgress(backendProgress.cancelled).percent, 0);

  const sandbox = backendFixture("sandbox.json");
  const fullProjection = projection.normalizeProjection(sandbox.complete);
  assert.strictEqual(projection.normalizePath({ type: "career", label: "就业规划" }).label, "就业");
  assert.strictEqual(projection.normalizePath({ type: "civil", label: "考公考编规划" }).label, "考公");
  assert.strictEqual(fullProjection.radar.available, true);
  assert.strictEqual(fullProjection.projections[0].milestones[0].text, "完成作品集与岗位访谈");
  assert.strictEqual(projection.normalizeProjection(sandbox.missing_matrix).radar.available, false);

  const reports = backendFixture("report.json");
  assert.strictEqual(report.normalizeReport(reports.complete).phases.length, 2);
  assert.strictEqual(report.normalizeReport(reports.legacy).phases[0].tasks[0].title, "整理院校清单");
  assert.strictEqual(report.normalizeReport(reports.no_action_plan).phases.length, 0);

  assert.deepStrictEqual(parseSseBlock("event: done\ndata: {\"finished\":true}"), { event: "done", data: { finished: true } });
  assert.deepStrictEqual(parseSseBlock("data: plain text"), { event: "message", data: "plain text" });

  const originalDecoder = global.TextDecoder;
  global.TextDecoder = undefined;
  const decoder = createDecoder();
  const encoded = Buffer.from("路径", "utf8");
  assert.strictEqual(decoder.decode(encoded.subarray(0, 2)), "");
  assert.strictEqual(decoder.decode(encoded.subarray(2, 4)), "路");
  assert.strictEqual(decoder.decode(encoded.subarray(4)), "径");
  global.TextDecoder = originalDecoder;

  const appConfig = JSON.parse(frontendFile("app.json"));
  assert.strictEqual(appConfig.darkmode, undefined);
  assert.strictEqual(appConfig.themeLocation, undefined);
  assert.match(frontendFile("styles/tokens.wxss"), /--color-primary:\s*#2868F5/);
  assert.match(frontendFile("pages/today/index.wxml"), /progress-arc/);
  assert.match(frontendFile("components/growth/progress-arc/index.wxml"), /type="2d"/);
  assert.doesNotMatch(frontendFile("components/growth/progress-arc/index.js"), /createCanvasContext/);
  assert.match(frontendFile("pages/today/index.wxml"), /weekBars/);
  assert.match(frontendFile("pages/action/index.wxml"), /phase-roadmap/);
  assert.match(frontendFile("pkg-growth/sandbox-result/index.wxml"), /comparisonRows/);
  assert.match(frontendFile("pkg-growth/sandbox-chat/index.js"), /sandboxService\.resume/);
  assert.match(frontendFile("pkg-growth/sandbox-chat/index.js"), /selectedLabels/);
  assert.match(frontendFile("pkg-growth/sandbox-chat/index.js"), /restoredMessages/);
  assert.match(frontendFile("pkg-growth/sandbox-chat/index.js"), /item\.value \|\| item\.name/);
  assert.match(frontendFile("pkg-growth/sandbox-chat/index.js"), /changePaths/);
  assert.match(frontendFile("pkg-growth/sandbox-chat/index.wxml"), /pathSelectionLocked/);
  assert.match(frontendFile("pkg-growth/sandbox-chat/index.wxml"), /本次对比/);
  assert.match(frontendFile("custom-tab-bar/index.wxml"), /activeIcon/);
  assert.match(frontendFile("utils/page.js"), /getHeroTop/);
  assert.doesNotMatch(frontendFile("custom-tab-bar/index.wxss"), /transition|transform/);
  assert.doesNotMatch(frontendFile("custom-tab-bar/index.js"), /vibrate/);
  assert.doesNotMatch(frontendFile("components/growth/path-coordinate-map/index.wxss"), /transition|:active|scale\(/);
  assert.doesNotMatch(frontendFile("pages/explore/index.js"), /vibrate/);
  assert.doesNotMatch(frontendFile("pkg-growth/sandbox-result/index.js"), /vibrate/);
  assert.match(frontendFile("pages/today/index.wxss"), /transform-origin:\s*0 0/);
  assert.match(frontendFile("pages/today/index.wxml"), /completion-note-band/);
  assert.match(frontendFile("pages/today/index.wxml"), /today-import/);
  assert.match(frontendFile("pages/today/index.wxml"), /task-row wx:for="{{todayTodos}}"/);
  assert.match(frontendFile("pages/today/index.wxss"), /-webkit-line-clamp:\s*3/);
  assert.match(frontendFile("pkg-today/import/index.js"), /"xls"/);
  assert.match(frontendFile("services/today-service.js"), /fileName/);
  assert.doesNotMatch(frontendFile("pkg-growth/coach/index.wxml"), /预计 20 分钟/);
  assert.match(frontendFile("components/base/state-view/index.wxss"), /justify-content:\s*center/);
  assert.match(frontendFile("components/base/mini-tabbar/index.wxml"), /mini-tab__icon/);
  assert.doesNotMatch(frontendFile("styles/tokens.wxss"), /#0A84FF/);

  process.stdout.write("frontend-v2 contracts: ok\n");
}

run();
