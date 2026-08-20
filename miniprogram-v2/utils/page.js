function selectTab(page, selected) {
  if (typeof page.getTabBar === "function" && page.getTabBar()) {
    const data = page.data || {};
    const hidden = Boolean(data.sheet || data.editing || data.confirmTask);
    page.getTabBar().setData({ selected, hidden });
  }
}

function setTabBarHidden(page, hidden) {
  if (typeof page.getTabBar === "function" && page.getTabBar()) {
    page.getTabBar().setData({ hidden: Boolean(hidden) });
  }
}

function showError(error, fallback) {
  wx.showToast({ title: (error && error.message) || fallback || "操作失败", icon: "none" });
}

function requireSession() {
  const session = require("../stores/session-store");
  if (!session.state.authenticated) {
    wx.reLaunch({ url: "/pages/auth/login/index" });
    return null;
  }
  return session.state;
}

function getHeroTop(extra) {
  let statusBarHeight = 24;
  let capsuleBottom = 0;
  try {
    const info = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
    statusBarHeight = Number(info.statusBarHeight || statusBarHeight);
    const capsule = wx.getMenuButtonBoundingClientRect ? wx.getMenuButtonBoundingClientRect() : null;
    capsuleBottom = capsule && capsule.bottom ? Number(capsule.bottom) : 0;
  } catch (error) { /* use the conservative fallback */ }
  return Math.ceil(Math.max(statusBarHeight + 44, capsuleBottom) + Number(extra || 10));
}

module.exports = { selectTab, setTabBarHidden, showError, requireSession, getHeroTop };
