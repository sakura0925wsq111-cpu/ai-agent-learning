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
  const override = env === "develop" ? wx.getStorageSync("ICAMPUS_V2_API_BASE_URL") : "";
  return String(override || API_BASE_URLS[env] || API_BASE_URLS.develop).replace(/\/$/, "");
}

module.exports = { API_BASE_URLS, getRuntimeEnv, getApiBaseUrl };
