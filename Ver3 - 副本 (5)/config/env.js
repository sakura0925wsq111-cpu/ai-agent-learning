// API endpoints are selected automatically by the WeChat release channel.
// Replace trial/release URLs with the HTTPS domains configured in WeChat MP.
const API_BASE_URLS = {
  develop: "http://127.0.0.1:8000",
  trial: "https://test-api.example.com",
  release: "https://api.example.com"
};

function getRuntimeEnv() {
  try {
    return wx.getAccountInfoSync().miniProgram.envVersion || "develop";
  } catch (err) {
    return "develop";
  }
}

function getApiBaseUrl() {
  const runtimeEnv = getRuntimeEnv();
  // Developer override is intentionally ignored in trial/release builds.
  const localOverride = runtimeEnv === "develop"
    ? wx.getStorageSync("API_BASE_URL")
    : "";
  return String(localOverride || API_BASE_URLS[runtimeEnv] || API_BASE_URLS.develop)
    .replace(/\/$/, "");
}

module.exports = { API_BASE_URLS, getApiBaseUrl, getRuntimeEnv };
