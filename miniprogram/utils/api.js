const app = getApp();

/**
 * 获取可用的规划 Agent 列表
 */
const getAgents = () => {
  return app.request({
    url: "/api/v1/growth/agents",
    method: "GET"
  });
};

/**
 * 启动沙盒多路径对比会话
 */
const startSandbox = (userId) => {
  return app.request({
    url: "/api/v1/sandbox/start",
    method: "POST",
    data: { user_id: userId }
  });
};

module.exports = {
  getAgents,
  startSandbox
};
