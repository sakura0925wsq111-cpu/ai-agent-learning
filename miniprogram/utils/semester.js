const STORAGE_KEY = "semesterStart";

function parseDateOnly(value) {
  if (typeof value !== "string") return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(year, month - 1, day);
  if (
    parsed.getFullYear() !== year ||
    parsed.getMonth() !== month - 1 ||
    parsed.getDate() !== day
  ) return null;
  return parsed;
}

function formatDateOnly(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return year + "-" + month + "-" + day;
}

function getAcademicWeek(semesterStart, targetDate) {
  const start = parseDateOnly(semesterStart);
  if (!start) return null;
  const targetSource = targetDate instanceof Date ? targetDate : new Date();
  const target = new Date(
    targetSource.getFullYear(),
    targetSource.getMonth(),
    targetSource.getDate()
  );
  const diffDays = Math.floor((target.getTime() - start.getTime()) / 86400000);
  if (diffDays < 0) return 0;
  return Math.floor(diffDays / 7) + 1;
}

function getStoredSemesterStart() {
  if (typeof wx === "undefined" || !wx.getStorageSync) return "";
  const value = wx.getStorageSync(STORAGE_KEY);
  return parseDateOnly(value) ? value : "";
}

function saveSemesterStart(value) {
  const parsed = parseDateOnly(value);
  if (!parsed) return false;
  if (typeof wx !== "undefined" && wx.setStorageSync) {
    wx.setStorageSync(STORAGE_KEY, formatDateOnly(parsed));
  }
  return true;
}

function getPickerBounds(referenceDate) {
  const current = referenceDate instanceof Date ? referenceDate : new Date();
  return {
    min: (current.getFullYear() - 2) + "-01-01",
    max: (current.getFullYear() + 1) + "-12-31"
  };
}

module.exports = {
  STORAGE_KEY,
  parseDateOnly,
  formatDateOnly,
  getAcademicWeek,
  getStoredSemesterStart,
  saveSemesterStart,
  getPickerBounds
};
