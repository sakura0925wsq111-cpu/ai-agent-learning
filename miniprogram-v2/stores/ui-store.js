const state = {
  online: true,
  city: wx.getStorageSync("ICAMPUS_V2_CITY") || "北京",
  reduceMotion: Boolean(wx.getStorageSync("ICAMPUS_V2_REDUCE_MOTION")),
  suggestionEnabled: wx.getStorageSync("ICAMPUS_V2_SUGGESTION") !== false,
  activeSheet: ""
};

function setOnline(value) { state.online = Boolean(value); }
function setCity(city) {
  state.city = String(city || "北京").trim() || "北京";
  wx.setStorageSync("ICAMPUS_V2_CITY", state.city);
}
function setPreference(key, value) {
  state[key] = value;
  const storage = {
    reduceMotion: "ICAMPUS_V2_REDUCE_MOTION",
    suggestionEnabled: "ICAMPUS_V2_SUGGESTION"
  }[key];
  if (storage) wx.setStorageSync(storage, value);
}
function openSheet(name) { state.activeSheet = name || ""; }
function closeSheet() { state.activeSheet = ""; }

module.exports = { state, setOnline, setCity, setPreference, openSheet, closeSheet };
