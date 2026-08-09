const app = getApp();

const TAG_CONFIG = {
  course: { text: "课程学习", class: "tag-blue" },
  ai_plan: { text: "AI计划", class: "tag-orange" },
  personal: { text: "个人规划", class: "tag-green" },
  exam: { text: "考试备考", class: "tag-purple" },
  internship: { text: "实习任务", class: "tag-cyan" },
  habit: { text: "习惯养成", class: "tag-red" },
  manual: { text: "自定义", class: "tag-gray" }
};

Page({
  data: {
    statusBarHeight: 44,
    activeTab: "pending",
    taskList: [],
    loading: false,
    userId: "",
    showModal: false, isEdit: false, editId: null,
    formTitle: "", formDate: "", formTime: "12:00",
    today: "",
    showDeleteModal: false, deleteId: null, deleteIndex: null,
    showLongPressHint: false
  },

  onLoad(options) {
    const info = wx.getSystemInfoSync();
    const now = new Date();
    this.setData({
      statusBarHeight: info.statusBarHeight,
      userId: wx.getStorageSync("userId") || app.globalData.userId || "",
      today: this.formatDateStr(now)
    });
    this.loadTasks();
    const hasShownHint = wx.getStorageSync("longPressHintShown");
    if (!hasShownHint) {
      this.setData({ showLongPressHint: true });
      wx.setStorageSync("longPressHintShown", true);
      setTimeout(() => { this.setData({ showLongPressHint: false }); }, 2000);
    }
  },

  onShow() {
    if (!this.data.loading && !this.data.showModal && !this.data.showDeleteModal) {
      this.loadTasks();
    }
  },

  formatDateStr(date) {
    const y = date.getFullYear();
    return y + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0");
  },

  switchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    if (tab === this.data.activeTab) return;
    this.setData({ activeTab: tab, loading: true });
    this.loadTasks();
  },

  async loadTasks() {
    this.setData({ loading: true });
    try {
      const res = await app.request({
        url: "/api/v1/todos?user_id=" + this.data.userId + "&status=" + this.data.activeTab
      });
      const list = (res && res.todos) ? res.todos : [];
      this.setData({
        taskList: list.map(item => this.formatTaskItem(item)),
        loading: false
      });
    } catch (err) {
      console.error("加载任务失败:", err);
      this.setData({ taskList: [], loading: false });
      wx.showToast({ title: "加载失败", icon: "none" });
    }
  },

  formatTaskItem(item) {
    const tagConfig = TAG_CONFIG[item.source] || TAG_CONFIG.manual;
    return {
      id: item.id, title: item.title || "", time: this.formatDeadline(item.deadline),
      deadline: item.deadline, rawDeadline: item.deadline,
      done: item.status === "done" || item.status === "archived",
      archived: item.status === "archived",
      source: item.source || "manual",
      tagText: tagConfig.text, tagClass: tagConfig.class,
      status: item.status
    };
  },

  formatDeadline(deadlineStr) {
    if (!deadlineStr) return "";
    const d = new Date(deadlineStr), now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diffDays = Math.round((target - today) / 86400000);
    const timeStr = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
    if (diffDays === 0) return "今天 " + timeStr + " 截止";
    if (diffDays === 1) return "明天 " + timeStr + " 截止";
    if (diffDays > 1) return diffDays + "天后 " + timeStr + " 截止";
    return d.getMonth() + 1 + "/" + d.getDate() + " " + timeStr;
  },

  // ========== 打勾完成 ==========
  async toggleTodo(e) {
    const { id, index } = e.currentTarget.dataset;
    const item = this.data.taskList[index];
    if (!item || item.done) return;

    // 乐观更新
    const newList = [...this.data.taskList];
    newList[index] = { ...newList[index], done: true, status: "done" };
    this.setData({ taskList: newList });

    try {
      await app.request({
        method: "POST",
        url: "/api/v1/todos/" + id + "/toggle?user_id=" + this.data.userId
      });
      wx.showToast({ title: "已完成", icon: "success", duration: 800 });
      setTimeout(() => {
        if (this.data.activeTab === "pending") { this.loadTasks(); }
      }, 500);
    } catch (err) {
      wx.showToast({ title: "操作失败", icon: "error" });
      const rollbackList = [...this.data.taskList];
      rollbackList[index] = { ...rollbackList[index], done: false, status: "pending" };
      this.setData({ taskList: rollbackList });
    }
  },

  // ========== 归档已完成 ==========
  async archiveTodo(e) {
    const { id, index } = e.currentTarget.dataset;
    const item = this.data.taskList[index];
    if (!item) return;

    try {
      await app.request({
        method: "POST",
        url: "/api/v1/todos/" + id + "/toggle?user_id=" + this.data.userId
      });
      wx.showToast({ title: "已归档", icon: "success", duration: 800 });
      setTimeout(() => { this.loadTasks(); }, 500);
    } catch (err) {
      wx.showToast({ title: "操作失败", icon: "error" });
    }
  },

  // ========== 恢复已归档 ==========
  async restoreTodo(e) {
    const { id } = e.currentTarget.dataset;
    try {
      await app.request({
        method: "POST",
        url: "/api/v1/todos/" + id + "/toggle?user_id=" + this.data.userId
      });
      wx.showToast({ title: "已恢复", icon: "success" });
      this.loadTasks();
    } catch (err) {
      wx.showToast({ title: "恢复失败", icon: "error" });
    }
  },

  // ========== 左滑删除 ==========
  onDeleteTap(e) {
    const { id, index } = e.currentTarget.dataset;
    this.setData({ showDeleteModal: true, deleteId: id, deleteIndex: index });
  },

  cancelDelete() {
    this.setData({ showDeleteModal: false, deleteId: null, deleteIndex: null });
  },

  async confirmDelete() {
    const { deleteId } = this.data;
    if (!deleteId) return;
    this.setData({ showDeleteModal: false });
    try {
      await app.request({
        method: "DELETE",
        url: "/api/v1/todos/" + deleteId + "?user_id=" + this.data.userId
      });
      wx.showToast({ title: "已删除", icon: "success" });
      this.loadTasks();
    } catch (err) {
      wx.showToast({ title: "删除失败", icon: "error" });
    }
    this.setData({ deleteId: null, deleteIndex: null });
  },

  // ========== 点击编辑 ==========
  onTaskTap(e) {
    const { id, index } = e.currentTarget.dataset;
    const item = this.data.taskList[index];
    if (!item) return;
    if (this.data.activeTab !== "pending") {
      wx.showToast({ title: "仅待完成任务可编辑", icon: "none" });
      return;
    }
    let formDate = "", formTime = "12:00";
    if (item.rawDeadline) {
      const d = new Date(item.rawDeadline);
      formDate = this.formatDateStr(d);
      formTime = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
    }
    this.setData({ showModal: true, isEdit: true, editId: id, formTitle: item.title, formDate: formDate, formTime: formTime });
  },

  // ========== FAB 新建 ==========
  onFabTap() {
    this.setData({ showModal: true, isEdit: false, editId: null, formTitle: "", formDate: "", formTime: "12:00" });
  },

  onTitleInput(e) { this.setData({ formTitle: e.detail.value }); },
  onDateChange(e) { this.setData({ formDate: e.detail.value }); },
  onTimeChange(e) { this.setData({ formTime: e.detail.value }); },
  closeModal() { this.setData({ showModal: false }); },

  async onSubmit() {
    const { formTitle, formDate, formTime, isEdit, editId, userId } = this.data;
    if (!formTitle.trim()) { wx.showToast({ title: "请输入任务标题", icon: "none" }); return; }

    let deadline = null;
    if (formDate) { deadline = formDate + "T" + (formTime || "00:00") + ":00"; }

    wx.showLoading({ title: isEdit ? "保存中..." : "创建中...", mask: true });
    try {
      if (isEdit) {
        await app.request({
          method: "PUT",
          url: "/api/v1/todos/" + editId + "?user_id=" + userId,
          data: { title: formTitle.trim(), deadline: deadline }
        });
      } else {
        await app.request({
          method: "POST",
          url: "/api/v1/todos?user_id=" + userId,
          data: { title: formTitle.trim(), deadline: deadline, source: "manual" }
        });
      }
      wx.hideLoading();
      wx.showToast({ title: isEdit ? "已保存" : "创建成功", icon: "success" });
      this.closeModal();
      this.loadTasks();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: isEdit ? "保存失败" : "创建失败", icon: "error" });
    }
  },

  async onRefresh() { await this.loadTasks(); wx.stopPullDownRefresh(); },
  goBack() { wx.navigateBack(); }
});
