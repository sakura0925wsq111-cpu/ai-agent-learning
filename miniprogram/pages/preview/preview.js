const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    navHeight: 0,
    importType: "course",
    importId: "",
    fileName: "",
    fileSize: "",
    previewList: [],
    isAllSelected: true,
    selectedCount: 0,
    importLoading: false
  },

  getUserId() {
    return app.globalData.userId || wx.getStorageSync("userId") || "";
  },

  onLoad(options) {
    const info = wx.getSystemInfoSync();
    const navHeight = info.statusBarHeight + 44;
    const { importType, importId, fileName, fileSize } = options;

    this.setData({
      statusBarHeight: info.statusBarHeight,
      navHeight: navHeight,
      importType: importType || "course",
      importId: importId || "",
      fileName: decodeURIComponent(fileName || ""),
      fileSize: decodeURIComponent(fileSize || "")
    });

    if (importId) {
      this.loadPreview(importId);
    }
  },

  async loadPreview(importId) {
    wx.showLoading({ title: "加载中..." });
    try {
      // Re-fetch or use stored preview - for now use local API call
      const res = await app.request({
        url: "/api/v1/today/import/preview?import_id=" + importId
      });
      if (res && res.items) {
        const list = res.items.map(item => ({ ...item, selected: true }));
        this.setData({
          previewList: list, isAllSelected: true, selectedCount: list.length
        });
      }
    } catch (err) {
      wx.showToast({ title: "加载预览失败", icon: "none" });
    }
    wx.hideLoading();
  },

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

  async onConfirm() {
    const { selectedCount, importLoading, importId } = this.data;
    if (selectedCount === 0 || importLoading || !importId) return;

    this.setData({ importLoading: true });
    try {
      const res = await app.request({
        method: "POST",
        url: "/api/v1/today/import/confirm",
        data: { import_id: importId }
      });
      wx.showToast({ title: "已导入 " + (res.saved_count || selectedCount) + " 项", icon: "success", duration: 2000 });
      setTimeout(() => { wx.switchTab({ url: "/pages/schedule/schedule" }); }, 2000);
    } catch (err) {
      console.error("确认导入失败:", err);
      wx.showToast({ title: err.message || "导入失败", icon: "error" });
      this.setData({ importLoading: false });
    }
  },

  goBack() { wx.navigateBack(); }
});