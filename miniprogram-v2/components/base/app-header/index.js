Component({
  properties: {
    title: { type: String, value: "iCampus" },
    eyebrow: { type: String, value: "" },
    back: { type: Boolean, value: false },
    actionLabel: { type: String, value: "" },
    compact: { type: Boolean, value: false }
  },
  data: { statusBarHeight: 24 },
  lifetimes: {
    attached() {
      const info = wx.getWindowInfo ? wx.getWindowInfo() : {};
      this.setData({ statusBarHeight: info.statusBarHeight || 24 });
    }
  },
  methods: {
    onBack() {
      this.triggerEvent("back");
    },
    onAction() {
      this.triggerEvent("action");
    }
  }
});
