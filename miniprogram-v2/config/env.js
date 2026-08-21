const API_BASE_URLS = {
  // Temporary HTTPS tunnel for real-device development testing. Remove or replace when it expires.
  develop: "https://virtue-investigators-stocks-prints.trycloudflare.com",
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
  // Temporary tunnel URLs can remain in simulator/device storage after a restart.
  const staleTunnel = env === "develop"
    && /(?:loca\.lt|trycloudflare\.com)$/i.test(override)
    && override !== API_BASE_URLS.develop;
  const selected = staleTunnel ? configured : (override || configured);
  return String(selected).replace(/\/$/, "");
}

module.exports = { API_BASE_URLS, getRuntimeEnv, getApiBaseUrl };
