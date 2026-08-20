const API_BASE_URLS = {
  // Temporary HTTPS tunnel for real-device development testing. Remove or replace when it expires.
  develop: "https://carter-headquarters-recreation-unknown.trycloudflare.com",
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
  const override = env === "develop" ? String(wx.getStorageSync("ICAMPUS_V2_API_BASE_URL") || "").trim() : "";
  const selected = override || API_BASE_URLS[env] || API_BASE_URLS.develop;
  // Ignore stale localtunnel consent URLs left in simulator/device storage.
  if (env === "develop" && /loca\.lt/i.test(selected)) return API_BASE_URLS.develop;
  return String(selected).replace(/\/$/, "");
}

module.exports = { API_BASE_URLS, getRuntimeEnv, getApiBaseUrl };
