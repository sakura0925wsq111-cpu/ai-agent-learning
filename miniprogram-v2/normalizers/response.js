function apiError(raw, status) {
  const code = raw && typeof raw.code !== "undefined" ? raw.code : status;
  const message = (raw && (raw.message || raw.detail)) || "请求失败";
  return { type: "api", status: status || 0, code, message, retryable: false };
}

function unwrapResponse(raw, status) {
  if (raw && typeof raw === "object" && Object.prototype.hasOwnProperty.call(raw, "code")) {
    if (raw.code !== 0) throw apiError(raw, status);
    return raw.data;
  }
  return raw;
}

function normalizeError(error, status) {
  if (error && error.type && error.message) return error;
  const message = (error && (error.message || error.errMsg || error.detail)) || "网络请求失败";
  const network = !status || /timeout|fail|abort|network/i.test(message);
  const friendlyMessage = /abort/i.test(message) ? "请求已取消" : network ? "暂时无法连接服务，请稍后重试" : message;
  return {
    type: network ? "network" : "http",
    status: status || 0,
    code: status || "NETWORK_ERROR",
    message: friendlyMessage,
    retryable: network || status >= 500
  };
}

module.exports = { apiError, unwrapResponse, normalizeError };
