const todayService = require("../../services/today-service");
const sessionStore = require("../../stores/session-store");
const { showError, requireSession, getHeroTop } = require("../../utils/page");

Page({
  data: { type: "course", file: null, stage: "idle", progress: 0, from: "", heroTop: 86 },
  onLoad(options) { if (!requireSession()) return; this.setData({ from: options.from || "", heroTop: getHeroTop(12) }); },
  onUnload() { if (this._upload && this._upload.cancel) this._upload.cancel(); },
  back() { wx.navigateBack(); },
  type(event) { if (this.data.stage === "idle") this.setData({ type: event.currentTarget.dataset.type, file: null }); },
  choose() {
    const extension = this.data.type === "course" ? ["pdf"] : ["xlsx", "xls", "pdf"];
    wx.chooseMessageFile({ count: 1, type: "file", extension, success: ({ tempFiles }) => { const file = tempFiles[0]; if (file) this.setData({ file: { name: file.name, path: file.path, sizeLabel: `${Math.max(1, Math.round(file.size / 1024))} KB` } }); } });
  },
  clearFile() { if (this.data.stage === "idle") this.setData({ file: null }); },
  async upload() {
    if (!this.data.file || this.data.stage !== "idle") return;
    this.setData({ stage: "uploading", progress: 0 });
    try {
      this._upload = todayService.importFile(sessionStore.state.userId, this.data.file.path, this.data.type, (progress) => this.setData({ progress, stage: progress >= 100 ? "parsing" : "uploading" }), this.data.file.name);
      const result = await this._upload;
      this.setData({ stage: "done" });
      wx.navigateTo({ url: `/pkg-today/import-preview/index?importId=${result.import_id}&from=${this.data.from}` });
    } catch (error) { this.setData({ stage: "idle", progress: 0 }); showError(error, "文件解析失败"); }
    finally { this._upload = null; }
  },
  cancel() { if (this._upload && this._upload.cancel) this._upload.cancel(); this.setData({ stage: "idle", progress: 0 }); }
});
