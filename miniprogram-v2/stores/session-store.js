const KEYS = {
  token: "ICAMPUS_V2_TOKEN",
  userId: "ICAMPUS_V2_USER_ID",
  user: "ICAMPUS_V2_USER"
};

const state = { token: "", userId: "", user: null, authenticated: false };
const listeners = [];

function emit() { listeners.slice().forEach((listener) => listener(state)); }

function restore() {
  state.token = wx.getStorageSync(KEYS.token) || "";
  state.userId = wx.getStorageSync(KEYS.userId) || "";
  state.user = wx.getStorageSync(KEYS.user) || null;
  state.authenticated = Boolean(state.token && state.userId);
  emit();
  return state;
}

function setSession(payload) {
  state.token = payload.token || "";
  state.userId = payload.user_id || payload.userId || "";
  state.user = payload.user || null;
  state.authenticated = Boolean(state.token && state.userId);
  wx.setStorageSync(KEYS.token, state.token);
  wx.setStorageSync(KEYS.userId, state.userId);
  wx.setStorageSync(KEYS.user, state.user);
  emit();
}

function updateUser(user) {
  state.user = user || null;
  wx.setStorageSync(KEYS.user, state.user);
  emit();
}

function clear() {
  state.token = "";
  state.userId = "";
  state.user = null;
  state.authenticated = false;
  Object.values(KEYS).forEach((key) => wx.removeStorageSync(key));
  emit();
}

function subscribe(listener) {
  listeners.push(listener);
  return () => {
    const index = listeners.indexOf(listener);
    if (index >= 0) listeners.splice(index, 1);
  };
}

module.exports = { KEYS, state, restore, setSession, updateUser, clear, subscribe };
