Component({
  properties: { counts: { type: Object, value: {} }, total: { type: Number, value: 0 } },
  data: { labels: { profile: "个人资料", goal: "目标", action: "行动", fact: "事实" } },
  observers: { "counts,total": function update() { const entries = Object.keys(this.data.labels).map((key) => ({ key, label: this.data.labels[key], count: Number(this.data.counts[key] || 0), width: this.data.total ? Math.round(Number(this.data.counts[key] || 0) / this.data.total * 100) : 0 })); this.setData({ entries }); } }
});
