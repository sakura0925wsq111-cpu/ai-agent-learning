const sessionStore = require("../stores/session-store");
const { unwrapResponse, normalizeError } = require("../normalizers/response");

function upload(options) {
  let task;
  let timer;
  const promise = new Promise((resolve, reject) => {
    const header = Object.assign({}, options.header || {});
    if (sessionStore.state.token) header.Authorization = `Bearer ${sessionStore.state.token}`;
    task = wx.uploadFile({
      url: `${getApp().globalData.baseUrl}${options.url}`,
      filePath: options.filePath,
      name: options.name || "file",
      formData: options.formData || {},
      header,
      success(res) {
        clearTimeout(timer);
        let body = res.data;
        try { body = typeof body === "string" ? JSON.parse(body) : body; }
        catch (error) { reject(normalizeError({ message: "服务端返回无法解析" }, res.statusCode)); return; }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try { resolve(unwrapResponse(body, res.statusCode)); }
          catch (error) { reject(error); }
          return;
        }
        reject(normalizeError(body, res.statusCode));
      },
      fail(error) { clearTimeout(timer); reject(normalizeError(error, 0)); }
    });
    if (task.onProgressUpdate && options.onProgress) {
      task.onProgressUpdate(({ progress }) => options.onProgress(Math.max(0, Math.min(100, progress))));
    }
    timer = setTimeout(() => {
      task.abort();
      reject(normalizeError({ message: "上传超时，请重试" }, 0));
    }, options.timeout || 60000);
  });
  promise.cancel = () => { clearTimeout(timer); if (task) task.abort(); };
  return promise;
}

module.exports = { upload };
