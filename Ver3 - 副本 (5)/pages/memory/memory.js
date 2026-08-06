const app = getApp();

Page({
  data: { statusBarHeight: 44, userId: "", memories: [], profileCount: 0, goalCount: 0, totalCount: 0 },

  onLoad() {
    const info = wx.getSystemInfoSync(); const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    this.setData({ statusBarHeight: info.statusBarHeight, userId }); this.loadMemories();
  },

  async loadMemories() {
    wx.showLoading({ title: "加载中..." });
    try {
      const res = await app.request({ url: `/api/v1/memory/panel/${this.data.userId}` });
      const memories = res.memories || [];
      const typeCounts = res.type_counts || {};
      this.setData({
        profileCount: typeCounts.profile || 0,
        goalCount: typeCounts.goal || 0,
        totalCount: res.total || memories.length
      });
      if (memories.length > 0) {
        this.setData({ memories: this.formatMemories(memories) });
      } else {
        await this.loadProfileFallback();
      }
    } catch (err) {
      await this.loadProfileFallback();
    }
    wx.hideLoading();
  },

  async loadProfileFallback() {
    try {
      const profile = await app.request({ url: `/api/v1/users/${this.data.userId}` });
      const fallbackMemories = [
        { key: "name", value: profile.name || "", memory_type: "profile", label: "姓名" },
        { key: "student_id", value: profile.student_id || "", memory_type: "profile", label: "学号" },
        { key: "school", value: profile.school || "", memory_type: "profile", label: "学校" },
        { key: "college", value: profile.college || "", memory_type: "profile", label: "学院" },
        { key: "major", value: profile.major || "", memory_type: "profile", label: "专业" },
        { key: "grade", value: profile.grade || "", memory_type: "profile", label: "年级" },
        { key: "enroll_year", value: profile.enroll_year || "", memory_type: "profile", label: "入学年份" },
      ].filter(function(m) { return m.value; });
      const profileCount = fallbackMemories.filter(m => m.memory_type === 'profile').length;
      this.setData({ memories: this.formatMemories(fallbackMemories), profileCount: profileCount, goalCount: 0, totalCount: fallbackMemories.length });
    } catch (e) {
      this.setData({ memories: [] });
    }
  },

  formatMemories(list) {
    const colors = { profile: "#4A90D9", goal: "#52C41A", action: "#FA8C16", fact: "#722ED1" };
    const labels = { name: "姓名", student_id: "学号", major: "专业", grade: "年级", school: "学校", college: "学院", enroll_year: "入学年份", target_school: "目标院校", target_job: "目标职业", strength: "核心优势", weakness: "待提升项", interest: "兴趣方向" };
    return list.map(item => ({ ...item, label: labels[item.key] || item.key, category: item.memory_type, color: colors[item.memory_type] || "#999" }));
  },

  editMemory(e) {
    const key = e.currentTarget.dataset.key; const memory = this.data.memories.find(m => m.key === key); if (!memory) return;
    wx.showModal({ title: `编辑：${memory.label}`, editable: true, placeholderText: memory.value,
      success: async (res) => {
        if (res.confirm && res.content) {
          wx.showLoading({ title: "保存中..." });
          try {
            await app.request({ method: "PATCH", url: `/api/v1/memory/panel/${this.data.userId}/${key}`, data: { value: res.content } });
            const memories = this.data.memories.map(m => m.key === key ? { ...m, value: res.content, updated_at: this.formatDate(new Date()) } : m);
            this.setData({ memories }); wx.showToast({ title: "已更新", icon: "success" });
          } catch (err) { wx.showToast({ title: "保存失败", icon: "none" }); }
          wx.hideLoading();
        }
      }
    });
  },

  async deleteMemory(e) {
    const key = e.currentTarget.dataset.key; const memory = this.data.memories.find(m => m.key === key); if (!memory) return;
    const res = await wx.showModal({ title: "删除确认", content: `确定删除「${memory.label}」吗？` }); if (!res.confirm) return;
    wx.showLoading({ title: "删除中..." });
    try {
      await app.request({ method: "DELETE", url: `/api/v1/memory/panel/${this.data.userId}/${key}` });
      this.setData({ memories: this.data.memories.filter(m => m.key !== key) }); wx.showToast({ title: "已删除", icon: "success" });
    } catch (err) { wx.showToast({ title: "删除失败", icon: "none" }); }
    wx.hideLoading();
  },

  addMemory() { wx.showToast({ title: "功能开发中", icon: "none" }); },
  formatDate(date) { const y = date.getFullYear(); const m = String(date.getMonth() + 1).padStart(2, "0"); const d = String(date.getDate()).padStart(2, "0"); return `${y}-${m}-${d}`; },
  goBack() { wx.navigateBack(); }
});