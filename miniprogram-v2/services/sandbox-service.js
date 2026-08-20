const { request } = require("./request");
const { stream } = require("./stream");
const q = encodeURIComponent;
function paths() { return request({ url: "/api/v1/sandbox/paths" }); }
function start(userId, selectedPaths) { return request({ method: "POST", url: "/api/v1/sandbox/start", data: { user_id: userId, paths: selectedPaths } }); }
function chat(userId, sessionId, message) { return request({ method: "POST", url: "/api/v1/sandbox/chat", data: { user_id: userId, session_id: sessionId, message } }); }
function chatStream(userId, sessionId, message, onEvent) { return stream({ url: "/api/v1/sandbox/chat/stream", data: { user_id: userId, session_id: sessionId, message }, onEvent }); }
function resume(userId, sessionId, state, message) { return request({ method: "POST", url: "/api/v1/sandbox/resume", data: { user_id: userId, session_id: sessionId, state, message: message || "" } }); }
function result(sessionId, userId) { return request({ url: `/api/v1/sandbox/result/${q(sessionId)}?user_id=${q(userId)}` }); }
module.exports = { paths, start, chat, chatStream, resume, result };
