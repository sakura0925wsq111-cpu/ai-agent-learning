const sessionStore = require("../stores/session-store");
const { normalizeError } = require("../normalizers/response");

function fallbackDecoder() {
  let carry = [];
  return {
    decode(chunk) {
      const incoming = Array.from(new Uint8Array(chunk));
      const bytes = carry.concat(incoming);
      let sequenceStart = bytes.length - 1;
      while (sequenceStart >= 0 && (bytes[sequenceStart] & 0xC0) === 0x80) sequenceStart -= 1;
      let expected = 1;
      const lead = bytes[sequenceStart];
      if (typeof lead === "number") {
        if ((lead & 0xF8) === 0xF0) expected = 4;
        else if ((lead & 0xF0) === 0xE0) expected = 3;
        else if ((lead & 0xE0) === 0xC0) expected = 2;
      }
      const incomplete = sequenceStart >= 0 && bytes.length - sequenceStart < expected;
      const cut = incomplete ? sequenceStart : bytes.length;
      carry = bytes.slice(cut);
      const complete = bytes.slice(0, cut);
      const encoded = complete.map((byte) => `%${byte.toString(16).padStart(2, "0")}`).join("");
      try { return decodeURIComponent(encoded); }
      catch (error) { return complete.map((byte) => String.fromCharCode(byte)).join(""); }
    }
  };
}

function createDecoder() {
  return typeof TextDecoder !== "undefined" ? new TextDecoder("utf-8") : fallbackDecoder();
}

function decodeChunk(chunk, decoder) {
  return decoder.decode(chunk, { stream: true });
}

function parseSseBlock(block) {
  let event = "message";
  const data = [];
  block.split(/\r?\n/).forEach((line) => {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  });
  const raw = data.join("\n");
  let payload = raw;
  try { payload = JSON.parse(raw); } catch (error) { /* text payload */ }
  return { event, data: payload };
}

function stream(options) {
  let task;
  let textBuffer = "";
  let settled = false;
  const decoder = createDecoder();
  const promise = new Promise((resolve, reject) => {
    const header = Object.assign({ "Content-Type": "application/json", Accept: "text/event-stream" }, options.header || {});
    if (sessionStore.state.token) header.Authorization = `Bearer ${sessionStore.state.token}`;
    task = wx.request({
      url: `${getApp().globalData.baseUrl}${options.url}`,
      method: options.method || "POST",
      data: options.data || {},
      header,
      enableChunked: true,
      timeout: options.timeout || 90000,
      success(res) {
        if (settled) return;
        settled = true;
        if (res.statusCode >= 200 && res.statusCode < 300) resolve();
        else reject(normalizeError(res.data, res.statusCode));
      },
      fail(error) {
        if (settled) return;
        settled = true;
        reject(normalizeError(error, 0));
      }
    });
    task.onChunkReceived(({ data }) => {
      textBuffer += decodeChunk(data, decoder).replace(/\r\n/g, "\n");
      let boundary = textBuffer.indexOf("\n\n");
      while (boundary >= 0) {
        const block = textBuffer.slice(0, boundary);
        textBuffer = textBuffer.slice(boundary + 2);
        if (block.trim() && options.onEvent) {
          try { options.onEvent(parseSseBlock(block)); }
          catch (error) {
            if (!settled) {
              settled = true;
              if (task && task.abort) task.abort();
              reject(normalizeError(error, 0));
            }
            return;
          }
        }
        boundary = textBuffer.indexOf("\n\n");
      }
    });
  });
  promise.cancel = () => { if (task) task.abort(); };
  return promise;
}

module.exports = { stream, parseSseBlock, createDecoder };
