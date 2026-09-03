const API_BASE_URLS = {
  develop: "http://127.0.0.1:8000",
  trial: "https://test-api.example.com",
  release: "https://api.example.com"
};

function getRuntimeEnv() {
  try {
    return wx.getAccountInfoSync().miniProgram.envVersion || "develop";
  } catch (error) {
    return "develop";
  }
}

function getApiBaseUrl() {
  const env = getRuntimeEnv();
  const configured = API_BASE_URLS[env] || API_BASE_URLS.develop;
  const override = env === "develop" ? String(wx.getStorageSync("ICAMPUS_V2_API_BASE_URL") || "").trim() : "";
  // Ignore tunnel addresses left in storage from earlier real-device debugging.
  const staleTunnel = env === "develop"
    && /(?:loca\.lt|trycloudflare\.com)$/i.test(override)
    && override !== API_BASE_URLS.develop;
  if (staleTunnel) {
    wx.removeStorageSync("ICAMPUS_V2_API_BASE_URL");
  }
  const selected = staleTunnel ? configured : (override || configured);
  return String(selected).replace(/\/$/, "");
}

module.exports = { API_BASE_URLS, getRuntimeEnv, getApiBaseUrl };
