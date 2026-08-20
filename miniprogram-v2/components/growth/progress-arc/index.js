Component({
  properties: { percent: { type: Number, value: 0 }, label: { type: String, value: "计划完成" } },
  observers: { percent() { wx.nextTick(() => this.draw()); } },
  lifetimes: { ready() { this.draw(); } },
  methods: {
    draw() {
      this.createSelectorQuery().select("#arcCanvas").fields({ node: true, size: true }).exec((result) => {
        const target = result && result[0];
        if (!target || !target.node || !target.width) return;
        const canvas = target.node;
        const ctx = canvas.getContext("2d");
        const info = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
        const dpr = info.pixelRatio || 1;
        canvas.width = target.width * dpr;
        canvas.height = target.height * dpr;
        ctx.scale(dpr, dpr);
        const p = Math.max(0, Math.min(100, Number(this.data.percent || 0)));
        const size = Math.min(target.width, target.height);
        const center = size / 2;
        const radius = size * 55 / 140;
        const start = -Math.PI / 2;
        const sweep = Math.PI * 2;
        ctx.lineCap = "round";
        ctx.lineWidth = size * 9 / 140;
        ctx.strokeStyle = "#CCD8F4";
        ctx.beginPath();
        ctx.arc(center, center, radius, start, start + sweep);
        ctx.stroke();
        if (p) {
          ctx.strokeStyle = "#2868F5";
          ctx.beginPath();
          ctx.arc(center, center, radius, start, start + sweep * p / 100);
          ctx.stroke();
        }
      });
    }
  }
});
