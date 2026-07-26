import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("D:/ai-agent-learning/Ver 2-1(沙盘API前)/Ver 2-1(沙盘API前)/pages/chatroom/chatroom.wxss", "r", encoding="utf-8") as f:
    content = f.read()

css_add = """
/* 路径多选卡片 */
.card-checkbox {
  font-size: 36rpx;
  margin-right: 16rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48rpx;
  height: 48rpx;
  flex-shrink: 0;
}

.card-selected {
  border-width: 3rpx !important;
  box-shadow: 0 0 12rpx rgba(74, 144, 217, 0.3);
}

.confirm-path-btn {
  margin-top: 24rpx;
  background: linear-gradient(135deg, #4A90D9, #7B68EE);
  color: #FFFFFF;
  border-radius: 24rpx;
  font-size: 28rpx;
  padding: 12rpx 0;
  text-align: center;
  width: 100%;
}
"""

content += css_add

with open("D:/ai-agent-learning/Ver 2-1(沙盘API前)/Ver 2-1(沙盘API前)/pages/chatroom/chatroom.wxss", "w", encoding="utf-8") as f:
    f.write(content)
print("CSS added")