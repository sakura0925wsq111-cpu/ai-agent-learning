const { cleanText } = require("../../../normalizers/text");

Component({
  properties: {
    role: { type: String, value: "assistant" },
    content: { type: String, value: "" },
    streaming: { type: Boolean, value: false }
  },
  data: { displayContent: "" },
  lifetimes: {
    attached() { this.setData({ displayContent: cleanText(this.data.content) }); }
  },
  observers: {
    content(value) { this.setData({ displayContent: cleanText(value) }); }
  }
});
