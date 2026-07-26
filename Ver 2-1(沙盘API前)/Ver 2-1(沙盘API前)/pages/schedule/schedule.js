Page({
  data: {
    statusBarHeight: 44,
    
    // 星期
    weekDays: [
      { name: '日' },
      { name: '一' },
      { name: '二' },
      { name: '三' },
      { name: '四' },
      { name: '五' },
      { name: '六' }
    ],
    
    // 日期（本周）
    days: [
      { date: 13, isToday: false },
      { date: 14, isToday: true },   // 今天
      { date: 15, isToday: false },
      { date: 16, isToday: false },
      { date: 17, isToday: false },
      { date: 18, isToday: false },
      { date: 19, isToday: false }
    ],
    
    // 日程列表（假数据）
    scheduleList: [
      {
        id: 1,
        time: '08:00',
        title: '高等数学（上）',
        location: '主教学楼 A201',
        status: 'active',
        statusText: '进行中',
        eventType: 'course',
        eventType: 'course',
        hasTodo: false
      },
      {
        id: 2,
        time: '10:00',
        title: '大学物理实验',
        location: '实验楼 B307',
        status: 'pending',
        statusText: '未开始',
        hasTodo: false
      },
      {
        id: 3,
        time: '14:00',
        title: '数据结构课后练习',
        location: '',
        status: 'active',
        statusText: '进行中',
        eventType: 'todo',
        hasTodo: true
      },
      {
        id: 4,
        time: '16:00',
        title: '英语阅读打卡',
        location: '',
        status: 'pending',
        statusText: '未开始',
        eventType: 'todo',
        hasTodo: true
      },
      {
        id: 5,
        time: '20:00',
        title: '复习高数错题',
        location: '',
        status: 'pending',
        statusText: '未开始',
        eventType: 'todo',
        hasTodo: true
      }
    ]
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    this.setData({
      statusBarHeight: info.statusBarHeight
    });
  },

  goBack() {
    wx.navigateBack();
  }
});
