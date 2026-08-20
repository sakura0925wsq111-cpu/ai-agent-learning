Component({
  properties: { paths: { type: Array, value: [] }, selected: { type: Array, value: [] }, max: { type: Number, value: 3 } },
  data: { viewPaths: [] },
  observers: {
    "paths,selected": function update(paths, selected) {
      const chosen = selected || [];
      const icons = { career: "▣", graduate: "◆", civil: "▥", major: "▤" };
      const labels = { career: "就业", graduate: "考研", civil: "考公", major: "转专业" };
      const descriptions = { career: "用项目、实习与岗位访谈验证职业方向", graduate: "评估研究兴趣、目标院校与备考投入", civil: "评估岗位偏好、考试准备与长期稳定性", major: "结合兴趣、基础与校内规则评估调整成本" };
      this.setData({ viewPaths: (paths || []).map((item) => Object.assign({}, item, { label: labels[item.type] || item.label, selected: chosen.indexOf(item.type) >= 0, icon: icons[item.type] || "◇", shortDescription: descriptions[item.type] || item.description })) });
    }
  },
  methods: { toggle(event) { this.triggerEvent("toggle", event.currentTarget.dataset.path); } }
});
