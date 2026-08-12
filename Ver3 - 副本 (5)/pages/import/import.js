const app = getApp();
const {
  formatDateOnly,
  getPickerBounds,
  getStoredSemesterStart,
  saveSemesterStart
} = require("../../utils/semester.js");

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 0,
    activeTab: "course",
    status: "idle",
    fileInfo: { name: "", size: "", path: "" },
    importId: "",
    previewList: [],
    isAllSelected: false,
    selectedCount: 0,
    errorMsg: "",
    confirmLoading: false,
    showFormatModal: false,
    mismatchMsg: "",
    semesterStart: "",
    semesterPickerValue: "",
    semesterStartMin: "",
    semesterStartMax: ""
  },

  getUserId() {
    return app.globalData.userId || wx.getStorageSync("userId") || "";
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    const pixelRatio = 750 / info.screenWidth;
    const navHeight = (info.statusBarHeight + 44 + 36) * pixelRatio;
    const bounds = getPickerBounds();
    this.setData({
      statusBarHeight: info.statusBarHeight,
      navHeight: navHeight,
      semesterStart: getStoredSemesterStart(),
      semesterPickerValue: formatDateOnly(new Date()),
      semesterStartMin: bounds.min,
      semesterStartMax: bounds.max
    });
  },

  goBack() { wx.navigateBack(); },

  switchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    if (tab === this.data.activeTab) return;
    this.setData({
      activeTab: tab, status: "idle",
      fileInfo: { name: "", size: "", path: "" },
      previewList: [], isAllSelected: false, selectedCount: 0, errorMsg: ""
    });
  },

  chooseFile() {
    const { activeTab } = this.data;
    if (activeTab === "course" && !this.data.semesterStart) {
      wx.showToast({ title: "请先设置开学日期", icon: "none" });
      return;
    }
    const extension = activeTab === "course" ? ["pdf"] : ["xlsx"];
    const expectType = activeTab === "course" ? "PDF" : "Excel";

    wx.chooseMessageFile({
      count: 1, type: "file", extension: extension,
      success: (res) => {
        const file = res.tempFiles[0];
        const fileName = file.name.toLowerCase();
        const isValidType = activeTab === "course"
          ? fileName.endsWith(".pdf")
          : fileName.endsWith(".xlsx");

        this.setData({
          fileInfo: { name: file.name, size: this.formatFileSize(file.size), path: file.path }
        });

        if (!isValidType) {
          const actualType = fileName.endsWith(".pdf") ? "PDF"
            : (fileName.endsWith(".xlsx") || fileName.endsWith(".xls")) ? "Excel" : "未知";
          this.setData({
            status: "type_mismatch",
            mismatchMsg: "当前选择\"" + (activeTab === "course" ? "课程表" : "考试表") + "\"导入，需要" + expectType + "格式文件，但检测到您上传的是" + actualType + "格式。请重新选择正确的文件类型。"
          });
          return;
        }

                wx.showModal({
          title: "覆盖确认",
          content: "导入新的课表将覆盖之前导入的内容，是否继续？",
          confirmText: "继续导入",
          cancelText: "取消",
          success: (modalRes) => {
            if (modalRes.confirm) {
              this.setData({ status: "selected" });
              this.uploadFile(file);
            } else {
              this.setData({
                fileInfo: { name: "", size: "", path: "" },
                status: "idle"
              });
            }
          }
        });
      },
      fail: (err) => { console.error("选择文件失败:", err); }
    });
  },

  formatFileSize(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  },

  // ========== 真实上传 ==========
  uploadFile(file) {
    this.setData({ status: "uploading" });
    const { activeTab } = this.data;
    const userId = this.getUserId();

    const semesterParam = this.data.semesterStart
      ? "&semester_start=" + encodeURIComponent(this.data.semesterStart)
      : "";
    const url = activeTab === "course"
      ? app.globalData.baseUrl + "/api/v1/today/import?user_id=" + userId + "&import_type=course" + semesterParam
      : app.globalData.baseUrl + "/api/v1/today/import/excel?user_id=" + userId;

    const formData = {};

    wx.uploadFile({
      url: url,
      filePath: file.path,
      name: "file",
      formData: formData,
      header: { "Authorization": "Bearer " + (app.globalData.token || "") },
      success: (uploadRes) => {
        try {
          const body = JSON.parse(uploadRes.data);
          if (uploadRes.statusCode < 200 || uploadRes.statusCode >= 300) {
            throw new Error(body.message || body.detail || "上传失败");
          }
          const data = body.data || body;

          if (data.import_id && data.items && data.items.length > 0) {
            const list = data.items.map(item => ({ ...item, selected: true }));
            this.setData({
              status: "parsed", importId: data.import_id,
              previewList: list, isAllSelected: true, selectedCount: list.length
            });
          } else if (data.import_id && (!data.items || data.items.length === 0)) {
            this.setData({ status: "parse_empty", importId: data.import_id });
          } else {
            throw new Error(data.message || "解析失败");
          }
        } catch (parseErr) {
          console.error("解析响应失败:", parseErr);
          this.setData({ status: "parse_error", errorMsg: "文件解析失败，请检查文件格式" });
        }
      },
      fail: (err) => {
        console.error("上传失败:", err);
        this.setData({ status: "parse_error", errorMsg: err.errMsg || "上传失败，请检查网络" });
      }
    });
  },

  // ========== 预览内的全选/单项选择 ==========
  toggleSelectAll() {
    const { isAllSelected, previewList } = this.data;
    const newSelected = !isAllSelected;
    const newList = previewList.map(item => ({ ...item, selected: newSelected }));
    this.setData({
      previewList: newList, isAllSelected: newSelected,
      selectedCount: newSelected ? newList.length : 0
    });
  },

  toggleItem(e) {
    const index = e.currentTarget.dataset.index;
    const newList = [...this.data.previewList];
    newList[index].selected = !newList[index].selected;
    const selectedCount = newList.filter(item => item.selected).length;
    this.setData({
      previewList: newList,
      isAllSelected: selectedCount === newList.length && newList.length > 0,
      selectedCount: selectedCount
    });
  },

  // ========== 确认导入 ==========
  async onConfirm() {
    const { selectedCount, confirmLoading, importId } = this.data;
    if (selectedCount === 0 || confirmLoading || !importId) return;

    this.setData({ confirmLoading: true });
    try {
      const res = await app.request({
        method: "POST",
        url: "/api/v1/today/import/confirm",
        data: {
          import_id: importId,
          selected_indexes: this.data.previewList
            .map((item, index) => item.selected ? index : -1)
            .filter(index => index >= 0)
        }
      });
      wx.showToast({ title: "已导入 " + (res.saved_count || selectedCount) + " 项", icon: "success", duration: 2000 });
      setTimeout(() => { wx.switchTab({ url: "/pages/schedule/schedule" }); }, 2000);
    } catch (err) {
      console.error("确认导入失败:", err);
      wx.showToast({ title: err.message || "导入失败", icon: "error" });
      this.setData({ confirmLoading: false });
    }
  },

  // ========== 重新选择 ==========
  onRetry() {
    this.setData({
      status: "idle",
      fileInfo: { name: "", size: "", path: "" },
      errorMsg: ""
    });
  },

  async onSemesterDateChange(e) {
    const semesterStart = e.detail.value;
    if (!saveSemesterStart(semesterStart)) return;
    this.setData({ semesterStart });

    const userId = this.getUserId();
    if (!userId) return;
    try {
      await app.request({
        method: "PUT",
        url: "/api/v1/today/courses/semester-settings?user_id=" + userId,
        data: { semester_start: semesterStart }
      });
      wx.showToast({ title: "开学日期已同步", icon: "success" });
    } catch (err) {
      console.error("同步开学日期失败:", err);
      wx.showToast({ title: "已保存，旧课表同步失败", icon: "none" });
    }
  },

  showFormatModal() { this.setData({ showFormatModal: true }); },
  hideFormatModal() { this.setData({ showFormatModal: false }); }
});
