const PROFILE_FIELDS = [
  { label: "姓名", field: "name", apiField: "name" },
  { label: "年级", field: "grade", apiField: "grade" },
  { label: "学院", field: "college", apiField: "college" },
  { label: "专业", field: "major", apiField: "major" },
  { label: "入学年份", field: "enrollYear", apiField: "enroll_year" }
];

function buildProfileList(user, includeNickname) {
  const fields = includeNickname
    ? [PROFILE_FIELDS[0], { label: "昵称", field: "nickname", apiField: "nickname" }, ...PROFILE_FIELDS.slice(1)]
    : PROFILE_FIELDS;
  return fields.map(item => ({
    label: item.label,
    field: item.field,
    value: user[item.apiField] || "未设置"
  }));
}

function toApiField(field) {
  return field === "enrollYear" ? "enroll_year" : field;
}

function persistUserField(app, apiField, value) {
  const stored = wx.getStorageSync("userInfo") || {};
  stored[apiField] = value;
  wx.setStorageSync("userInfo", stored);
  app.globalData.userInfo = stored;
}

module.exports = { buildProfileList, persistUserField, toApiField };
