const KEY = "ICAMPUS_V2_DEVICE_ID";

function getDeviceId() {
  let value = String(wx.getStorageSync(KEY) || "").trim();
  if (!value) {
    value = `mp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
    wx.setStorageSync(KEY, value);
  }
  return value;
}

module.exports = { KEY, getDeviceId };
