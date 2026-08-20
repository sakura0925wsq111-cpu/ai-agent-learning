const sessionStore = require("../stores/session-store");
const uiStore = require("../stores/ui-store");
const { unwrapResponse, normalizeError } = require("../normalizers/response");

const pendingGets = new Map();
let redirecting = false;

function baseUrl() {
  try { return getApp().globalData.baseUrl || ""; } catch (error) { return ""; }
}

function request(options) {
  if (!uiStore.state.online) {
    const offline = Promise.reject({ type: "offline", status: 0, code: "OFFLINE", message: "当前处于离线状态，请恢复网络后重试", retryable: true });
    offline.cancel = () => {};
    return offline;
  }
  const method = String(options.method || "GET").toUpperCase();
  const url = options.url || "";
  const dedupeKey = method === "GET" ? `${method}:${url}` : "";
  if (dedupeKey && pendingGets.has(dedupeKey)) return pendingGets.get(dedupeKey);

  let task = null;
  let cancelled = false;
  let attempt = 0;
  const retries = method === "GET" ? 1 : 0;

  const promise = new Promise((resolve, reject) => {
    const run = () => {
      attempt += 1;
      const headers = Object.assign({ "Content-Type": "application/json" }, options.header || {});
      if (sessionStore.state.token) headers.Authorization = `Bearer ${sessionStore.state.token}`;
      task = wx.request({
        url: `${baseUrl()}${url}`,
        method,
        data: options.data || {},
        header: headers,
        timeout: options.timeout || 60000,
        success(res) {
          if (cancelled) return;
          const status = res.statusCode || 0;
          const isLogin = url === "/api/v1/users/login";
          if (status === 401 && !isLogin && options.authRedirect !== false) {
            sessionStore.clear();
            if (!redirecting) {
              redirecting = true;
              wx.reLaunch({
                url: "/pages/auth/login/index",
                complete: () => { redirecting = false; }
              });
            }
          }
          if (status >= 200 && status < 300) {
            try { resolve(unwrapResponse(res.data, status)); }
            catch (error) { reject(error); }
            return;
          }
          reject(normalizeError(res.data, status));
        },
        fail(error) {
          if (cancelled) {
            reject(normalizeError({ message: "请求已取消" }, 0));
            return;
          }
          if (attempt <= retries) {
            run();
            return;
          }
          reject(normalizeError(error, 0));
        }
      });
    };
    run();
  });
  promise.cancel = () => {
    cancelled = true;
    if (task && typeof task.abort === "function") task.abort();
  };
  if (dedupeKey) {
    pendingGets.set(dedupeKey, promise);
    promise.then(
      () => pendingGets.delete(dedupeKey),
      () => pendingGets.delete(dedupeKey)
    );
  }
  return promise;
}

function createRequestScope() {
  const active = [];
  return {
    request(options) {
      const promise = request(options);
      active.push(promise);
      promise.then(
        () => active.splice(active.indexOf(promise), 1),
        () => active.splice(active.indexOf(promise), 1)
      );
      return promise;
    },
    cancelAll() {
      active.slice().forEach((promise) => promise.cancel && promise.cancel());
      active.length = 0;
    }
  };
}

module.exports = { request, createRequestScope };
