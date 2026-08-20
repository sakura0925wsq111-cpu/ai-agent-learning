Component({
  data: {
    selected: 0,
    tabs: [
      { pagePath: "/pages/today/index", text: "今天", icon: "/assets/icons/today.svg", activeIcon: "/assets/icons/today-active.svg" },
      { pagePath: "/pages/explore/index", text: "探索", icon: "/assets/icons/explore.svg", activeIcon: "/assets/icons/explore-active.svg" },
      { pagePath: "/pages/action/index", text: "行动", icon: "/assets/icons/action.svg", activeIcon: "/assets/icons/action-active.svg" },
      { pagePath: "/pages/passport/index", text: "我的", icon: "/assets/icons/profile.svg", activeIcon: "/assets/icons/profile-active.svg" }
    ]
  },
  methods: {
    switchTab(event) {
      const index = Number(event.currentTarget.dataset.index);
      const tab = this.data.tabs[index];
      if (!tab || index === this.data.selected) return;
      wx.switchTab({ url: tab.pagePath });
    }
  }
});
