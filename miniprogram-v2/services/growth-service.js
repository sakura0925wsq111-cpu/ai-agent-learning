const { request } = require("./request");
const { stream } = require("./stream");
const q = encodeURIComponent;
function dashboard(userId) { return request({ url: `/api/v1/growth/dashboard/${q(userId)}` }); }
function start(userId, agent, sandboxSessionId) { return request({ method: "POST", url: "/api/v1/growth/start", data: { user_id: userId, agent, sandbox_session_id: sandboxSessionId || null } }); }
function chat(userId, agent, sessionId, message) { return request({ method: "POST", url: "/api/v1/growth/chat", data: { user_id: userId, agent, session_id: sessionId, message } }); }
function chatStream(userId, agent, sessionId, message, onEvent) { return stream({ url: "/api/v1/growth/chat/stream", data: { user_id: userId, agent, session_id: sessionId, message }, onEvent }); }
function session(sessionId) { return request({ url: `/api/v1/growth/session/${q(sessionId)}` }); }
function report(sessionId) { return request({ url: `/api/v1/growth/report/${q(sessionId)}` }); }
function reports(userId) { return request({ url: `/api/v1/growth/reports?user_id=${q(userId)}` }); }
function history(userId) { return request({ url: `/api/v1/growth/history/${q(userId)}` }); }
function conversation(sessionId) { return request({ url: `/api/v1/growth/conversation/${q(sessionId)}` }); }
function qa(userId, agent, sessionId, message) { return request({ method: "POST", url: "/api/v1/growth/qa", data: { user_id: userId, agent, session_id: sessionId, message } }); }
function qaStream(userId, agent, sessionId, message, onEvent) { return stream({ url: "/api/v1/growth/qa/stream", data: { user_id: userId, agent, session_id: sessionId, message }, onEvent }); }
function correct(userId, sessionId, correction) { return request({ method: "POST", url: "/api/v1/growth/correct", data: { user_id: userId, session_id: sessionId, correction } }); }
function approve(userId, sessionId) { return request({ method: "POST", url: "/api/v1/growth/approve", data: { user_id: userId, session_id: sessionId } }); }
module.exports = { dashboard, start, chat, chatStream, session, report, reports, history, conversation, qa, qaStream, correct, approve };
