Component({
  properties: {
    state: { type: String, value: "empty" },
    title: { type: String, value: "暂无内容" },
    message: { type: String, value: "" },
    actionLabel: { type: String, value: "重试" }
  },
  methods: { action() { this.triggerEvent("action"); } }
});
