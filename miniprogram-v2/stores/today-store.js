const state = {
  selectedDate: "",
  viewMode: "timeline",
  overview: null,
  timeline: null,
  calendar: null,
  todos: [],
  updatedAt: {}
};

function fresh(key, ttl) {
  return Boolean(state[key] && Date.now() - (state.updatedAt[key] || 0) < ttl);
}

function set(key, value) {
  state[key] = value;
  state.updatedAt[key] = Date.now();
  return value;
}

function invalidate(keys) {
  (keys || Object.keys(state.updatedAt)).forEach((key) => delete state.updatedAt[key]);
}

module.exports = { state, fresh, set, invalidate };
