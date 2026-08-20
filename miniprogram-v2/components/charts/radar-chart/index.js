const COLORS = ["#2868F5", "#20AFC4", "#F59E42", "#24B47E"];
Component({
  properties: { dimensions: { type: Array, value: [] }, series: { type: Array, value: [] }, max: { type: Number, value: 10 } },
  observers: { "dimensions,series,max": function drawLater() { wx.nextTick(() => this.draw()); } },
  lifetimes: { ready() { this.draw(); } },
  methods: {
    draw() {
      const dimensions = this.data.dimensions || [];
      if (dimensions.length < 3 || !(this.data.series || []).length) return;
      const ctx = wx.createCanvasContext("radarCanvas", this);
      const center = 150, radius = 104, count = dimensions.length;
      ctx.clearRect(0, 0, 300, 300);
      ctx.setLineWidth(1); ctx.setStrokeStyle("#464D59");
      [0.25, 0.5, 0.75, 1].forEach((level) => {
        ctx.beginPath();
        for (let index = 0; index < count; index += 1) {
          const angle = -Math.PI / 2 + index * Math.PI * 2 / count;
          const x = center + Math.cos(angle) * radius * level;
          const y = center + Math.sin(angle) * radius * level;
          index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
        }
        ctx.closePath(); ctx.stroke();
      });
      dimensions.forEach((label, index) => {
        const angle = -Math.PI / 2 + index * Math.PI * 2 / count;
        ctx.beginPath(); ctx.moveTo(center, center); ctx.lineTo(center + Math.cos(angle) * radius, center + Math.sin(angle) * radius); ctx.stroke();
        ctx.setFillStyle("#D8DCE3"); ctx.setFontSize(11); ctx.setTextAlign(Math.cos(angle) > .2 ? "left" : Math.cos(angle) < -.2 ? "right" : "center");
        ctx.fillText(String(label).slice(0, 8), center + Math.cos(angle) * (radius + 15), center + Math.sin(angle) * (radius + 15) + 4);
      });
      (this.data.series || []).forEach((serie, serieIndex) => {
        const color = COLORS[serieIndex % COLORS.length]; ctx.beginPath();
        (serie.values || []).forEach((value, index) => {
          const angle = -Math.PI / 2 + index * Math.PI * 2 / count;
          const scaled = Math.min(this.data.max, Math.max(0, Number(value))) / this.data.max;
          const x = center + Math.cos(angle) * radius * scaled;
          const y = center + Math.sin(angle) * radius * scaled;
          index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
        });
        ctx.closePath(); ctx.setStrokeStyle(color); ctx.setLineWidth(2); ctx.stroke();
        ctx.setGlobalAlpha(0.16); ctx.setFillStyle(color); ctx.fill(); ctx.setGlobalAlpha(1);
      });
      ctx.draw();
    }
  }
});
