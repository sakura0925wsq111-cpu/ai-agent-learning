function normalizeDateStr(year, month, day) {
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return y + "-" + m + "-" + d;
}

module.exports = { normalizeDateStr };
