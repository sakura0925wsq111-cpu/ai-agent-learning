// ========== 原有功能（保留）==========

const formatNumber = n => {
  n = n.toString();
  return n[1] ? n : `0${n}`;
};

const formatTime = date => {
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hour = date.getHours();
  const minute = date.getMinutes();
  const second = date.getSeconds();

  return `${[year, month, day].map(formatNumber).join('/')} ${[hour, minute, second].map(formatNumber).join(':')}`;
};

// ========== 新增：日期格式化（项目常用）==========

/**
 * 格式化为 YYYY-MM-DD
 */
const formatDate = (date) => {
  const d = typeof date === 'string' ? new Date(date) : date;
  const year = d.getFullYear();
  const month = d.getMonth() + 1;
  const day = d.getDate();
  return `${year}-${formatNumber(month)}-${formatNumber(day)}`;
};

/**
 * 格式化为 YYYY-MM-DD HH:mm
 */
const formatDateTime = (date) => {
  const d = typeof date === 'string' ? new Date(date) : date;
  const year = d.getFullYear();
  const month = d.getMonth() + 1;
  const day = d.getDate();
  const hour = d.getHours();
  const minute = d.getMinutes();
  return `${year}-${formatNumber(month)}-${formatNumber(day)} ${formatNumber(hour)}:${formatNumber(minute)}`;
};

/**
 * 格式化为 MM-DD HH:mm（今日模式常用）
 */
const formatShortDateTime = (date) => {
  const d = typeof date === 'string' ? new Date(date) : date;
  const month = d.getMonth() + 1;
  const day = d.getDate();
  const hour = d.getHours();
  const minute = d.getMinutes();
  return `${formatNumber(month)}-${formatNumber(day)} ${formatNumber(hour)}:${formatNumber(minute)}`;
};

/**
 * 获取相对时间描述
 */
const getRelativeTime = (dateStr) => {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now - date;
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  if (hours < 24) return `${hours}小时前`;
  if (days < 7) return `${days}天前`;
  return formatDate(date);
};

// ========== 新增：时间段问候语（首页用）==========

const getGreeting = () => {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 9) return { text: '早上好，开启元气满满的一天～', icon: '🌅' };
  if (hour >= 9 && hour < 12) return { text: '上午好，今天课程多吗？', icon: '☀️' };
  if (hour >= 12 && hour < 14) return { text: '中午好，记得午休哦', icon: '🍱' };
  if (hour >= 14 && hour < 18) return { text: '下午好，专注效率最高的时候', icon: '☕' };
  if (hour >= 18 && hour < 22) return { text: '晚上好，今天收获如何？', icon: '🌆' };
  return { text: '夜深了，早点休息吧', icon: '🌙' };
};

// ========== 新增：课程节次转时间（今日模式用）==========

const nodeToTime = (startNode, endNode) => {
  const timeMap = {
    1: '08:00', 2: '09:50', 3: '10:10', 4: '12:00',
    5: '14:00', 6: '15:50', 7: '16:10', 8: '18:00',
    9: '19:00', 10: '10:00', 11: '14:00', 12: '08:00'
  };
  
  const start = timeMap[startNode] || '00:00';
  const end = timeMap[endNode] || '00:00';
  
  // 考试特殊处理
  if (startNode >= 10) {
    return { start, duration: 120 }; // 考试2小时
  }
  if (startNode >= 1 && startNode <= 9) {
    return { start, duration: 90 }; // 课程1.5小时
  }
  return { start, duration: 60 }; // 默认1小时
};

// ========== 新增：进度条渲染（成长模式用）==========

const renderProgressBlocks = (percent, total = 10) => {
  const filled = Math.round(percent / 10);
  const empty = total - filled;
  return '█'.repeat(filled) + '░'.repeat(empty);
};

// ========== 新增：数据校验（表单用）==========

const validators = {
  // 非空
  required: (value, message = '此项必填') => {
    if (value === undefined || value === null || value === '') {
      return message;
    }
    return null;
  },
  
  // 手机号
  phone: (value) => {
    if (!/^1[3-9]\d{9}$/.test(value)) {
      return '请输入正确的手机号';
    }
    return null;
  },
  
  // 邮箱
  email: (value) => {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
      return '请输入正确的邮箱';
    }
    return null;
  },
  
  // 时间范围
  timeRange: (start, end) => {
    if (start >= end) {
      return '结束时间必须晚于开始时间';
    }
    return null;
  }
};

/**
 * 执行表单校验
 */
const validate = (rules, values) => {
  const errors = {};
  for (const key in rules) {
    const ruleList = rules[key];
    for (const rule of ruleList) {
      const { validator, message, params } = rule;
      const value = values[key];
      const error = validator(value, ...(params || []), message);
      if (error) {
        errors[key] = error;
        break;
      }
    }
  }
  return {
    valid: Object.keys(errors).length === 0,
    errors
  };
};

// ========== 新增：节流/防抖（交互优化用）==========

const throttle = (fn, delay = 500) => {
  let lastTime = 0;
  return function (...args) {
    const now = Date.now();
    if (now - lastTime >= delay) {
      lastTime = now;
      fn.apply(this, args);
    }
  };
};

const debounce = (fn, delay = 500) => {
  let timer = null;
  return function (...args) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      fn.apply(this, args);
    }, delay);
  };
};

// ========== 新增：安全存储（替代 wx.storage 防异常）==========

const safeStorage = {
  set: (key, value) => {
    try {
      wx.setStorageSync(key, value);
      return true;
    } catch (e) {
      console.error('Storage set failed:', e);
      return false;
    }
  },
  
  get: (key, defaultValue = null) => {
    try {
      return wx.getStorageSync(key) || defaultValue;
    } catch (e) {
      console.error('Storage get failed:', e);
      return defaultValue;
    }
  },
  
  remove: (key) => {
    try {
      wx.removeStorageSync(key);
      return true;
    } catch (e) {
      console.error('Storage remove failed:', e);
      return false;
    }
  }
};

// ========== 导出 ==========

module.exports = {
  // 原有
  formatTime,
  formatNumber,
  
  // 日期
  formatDate,
  formatDateTime,
  formatShortDateTime,
  getRelativeTime,
  
  // 业务
  getGreeting,
  nodeToTime,
  renderProgressBlocks,
  
  // 表单
  validators,
  validate,
  
  // 性能
  throttle,
  debounce,
  
  // 存储
  safeStorage
};
