const ACTION_PREFIX = /(?:^|[。！？\n])\s*下一步行动\s*[：:]\s*([^\n]+)/g;
const ACTION_VERB = /^(完成|整理|投递|联系|复盘|练习|提交|制作|阅读|学习|更新|梳理|查询|申请|预约|准备|编写|测试|部署|收集|对照|列出|建立|发送|修改|安排|创建|报名|分析|确认)/;
const NON_TASK_MARKERS = ["？", "?", "还是", "要不要", "是否", "如果", "可以", "建议", "需要我", "你先", "你更", "选择", "吗"];

function taskFromCoachReply(text) {
  const source = String(text || "");
  const matches = Array.from(source.matchAll(ACTION_PREFIX));
  if (!matches.length) return "";
  const task = String(matches[matches.length - 1][1] || "").trim().replace(/[。！]+$/, "");
  if (task.length < 6 || task.length > 120) return "";
  if (!ACTION_VERB.test(task) || NON_TASK_MARKERS.some((marker) => task.includes(marker))) return "";
  return task;
}

module.exports = { taskFromCoachReply };
