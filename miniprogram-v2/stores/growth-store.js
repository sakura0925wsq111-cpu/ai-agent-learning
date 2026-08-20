const SANDBOX_KEY = "ICAMPUS_V2_SANDBOX_SESSION";
const PLANNING_KEY = "ICAMPUS_V2_PLANNING_SESSION";
const state = {
  dashboard: null,
  sandboxSession: null,
  planningSession: null,
  report: null,
  progress: null,
  updatedAt: {}
};

function restore() {
  state.sandboxSession = wx.getStorageSync(SANDBOX_KEY) || null;
  state.planningSession = wx.getStorageSync(PLANNING_KEY) || null;
  return state;
}

function set(key, value) {
  state[key] = value;
  state.updatedAt[key] = Date.now();
  if (key === "sandboxSession") wx.setStorageSync(SANDBOX_KEY, value || "");
  if (key === "planningSession") wx.setStorageSync(PLANNING_KEY, value || "");
  return value;
}

function fresh(key, ttl) {
  return Boolean(state[key] && Date.now() - (state.updatedAt[key] || 0) < ttl);
}

function invalidate(keys) {
  (keys || Object.keys(state.updatedAt)).forEach((key) => delete state.updatedAt[key]);
}

function clearSandbox() {
  state.sandboxSession = null;
  wx.removeStorageSync(SANDBOX_KEY);
}

module.exports = { state, restore, set, fresh, invalidate, clearSandbox };
