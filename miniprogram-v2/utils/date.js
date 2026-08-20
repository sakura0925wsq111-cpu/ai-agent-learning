function pad(value) { return String(value).padStart(2, "0"); }

function toDateKey(input) {
  const date = input instanceof Date ? input : new Date(input || Date.now());
  if (Number.isNaN(date.getTime())) return "";
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function formatDate(input, includeYear) {
  const date = new Date(input);
  if (Number.isNaN(date.getTime())) return "未安排日期";
  const prefix = includeYear ? `${date.getFullYear()}年` : "";
  return `${prefix}${date.getMonth() + 1}月${date.getDate()}日`;
}

function weekday(input) {
  const date = input instanceof Date ? input : new Date(input);
  return ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][date.getDay()];
}

function monthRange(input) {
  const date = input instanceof Date ? input : new Date(input || Date.now());
  return { year: date.getFullYear(), month: date.getMonth() + 1 };
}

module.exports = { toDateKey, formatDate, weekday, monthRange };
