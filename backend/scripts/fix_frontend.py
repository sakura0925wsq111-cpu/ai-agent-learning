import sys
sys.stdout.reconfigure(encoding="utf-8")

frontend_base = "D:/ai-agent-learning/Ver 2-1(沙盘API前)/Ver 2-1(沙盘API前)/pages/chatroom"

# ═══════════════════════════════════════════════════════════════
# Fix: chatroom.js - add multi-select path card logic
# ═══════════════════════════════════════════════════════════════
with open(f"{frontend_base}/chatroom.js", "r", encoding="utf-8") as f:
    content = f.read()

# Add selectedPaths to data
old_data = """  data: {
    statusBarHeight: 44, mode: "sandbox", agent: "career", sessionId: "", userId: "",
    messages: [], inputValue: "", isLoading: false, showQuickActions: true, showCards: false, cards: [], scrollToView: "",
    waitingForReady: false, waitingForTrigger: false,
    quickOptions: ["转专业", "考研规划", "考公评估", "就业指导"]
  },"""

new_data = """  data: {
    statusBarHeight: 44, mode: "sandbox", agent: "career", sessionId: "", userId: "",
    messages: [], inputValue: "", isLoading: false, showQuickActions: true, showCards: false, cards: [], scrollToView: "",
    waitingForReady: false, waitingForTrigger: false,
    selectingPaths: false, selectedPaths: [], 
    quickOptions: ["转专业", "考研规划", "考公评估", "就业指导"]
  },"""

content = content.replace(old_data, new_data)

# Modify the sandbox response handler to detect path selection mode
old_sandbox_handler = """    if (isSandbox) {
      app.request({
        method: "POST", url: "/sandbox/chat",
        data: { session_id: this.data.sessionId, user_id: this.data.userId, message: content }
      }).then(function(res) {
        if (res.session_id && !that.data.sessionId) that.setData({ sessionId: res.session_id });
        if (res.show_cards && res.cards && res.cards.length) {
          that.addMessage("assistant", res.report_text || res.message);
          that.setData({ showCards: true, cards: res.cards, showQuickActions: false, isLoading: false });
        } else {
          that.addMessage("assistant", res.message || "收到你的消息，让我想想...");
          that.setData({ isLoading: false });
        }
      }).catch(function() {
        that.addMessage("assistant", "网络异常，请重试");
        that.setData({ isLoading: false });
      });
      return;
    }"""

new_sandbox_handler = """    if (isSandbox) {
      app.request({
        method: "POST", url: "/sandbox/chat",
        data: { session_id: this.data.sessionId, user_id: this.data.userId, message: content }
      }).then(function(res) {
        if (res.session_id && !that.data.sessionId) that.setData({ sessionId: res.session_id });
        if (res.show_cards && res.cards && res.cards.length) {
          that.addMessage("assistant", res.report_text || res.message);
          // Check if this is path selection (no match_score) vs result cards (has match_score)
          var isSelecting = res.phase === "path_probe" && !res.finished;
          that.setData({ 
            showCards: true, cards: res.cards, showQuickActions: false, isLoading: false,
            selectingPaths: isSelecting, selectedPaths: []
          });
        } else {
          that.addMessage("assistant", res.message || "收到你的消息，让我想想...");
          that.setData({ isLoading: false, selectingPaths: false });
        }
      }).catch(function() {
        that.addMessage("assistant", "网络异常，请重试");
        that.setData({ isLoading: false });
      });
      return;
    }"""

content = content.replace(old_sandbox_handler, new_sandbox_handler)

# Add path selection handlers before goBack
old_goback = """  goBack: function() { wx.navigateBack(); }

});"""

new_goback = """  // ── Path selection for sandbox ──
  togglePathCard: function(e) {
    var type = e.currentTarget.dataset.type;
    var selected = this.data.selectedPaths.slice();
    var idx = selected.indexOf(type);
    if (idx >= 0) {
      selected.splice(idx, 1);
    } else {
      selected.push(type);
    }
    this.setData({ selectedPaths: selected });
  },

  confirmPathSelection: function() {
    var that = this;
    var selected = this.data.selectedPaths;
    if (selected.length === 0) {
      wx.showToast({ title: "请至少选择一个方向", icon: "none" });
      return;
    }
    var pathNames = [];
    var nameMap = { career: "就业", graduate: "考研", civil: "考公", major: "转专业" };
    selected.forEach(function(s) { pathNames.push(nameMap[s] || s); });
    var msg = "开始比对 " + pathNames.join("和");
    this.setData({ inputValue: msg, showCards: false, selectingPaths: false, selectedPaths: [] });
    this.sendMessage();
  },

  goBack: function() { wx.navigateBack(); }

});"""

content = content.replace(old_goback, new_goback)

with open(f"{frontend_base}/chatroom.js", "w", encoding="utf-8") as f:
    f.write(content)
print("chatroom.js updated with multi-select logic")

# ═══════════════════════════════════════════════════════════════
# Fix: chatroom.wxml - show multi-select cards for path selection
# ═══════════════════════════════════════════════════════════════
with open(f"{frontend_base}/chatroom.wxml", "r", encoding="utf-8") as f:
    content = f.read()

# Add path selection cards section before the result cards section
old_cards = """<!-- 内联方向卡片（沙盘完成后自动弹出）-->
<view wx:if="{{showCards}}" class="cards-section">
  <view class="cards-title">选择一个方向，开始深度规划</view>"""

new_cards = """<!-- 路径多选卡片（沙盘选择对比路径）-->
<view wx:if="{{showCards && selectingPaths}}" class="cards-section">
  <view class="cards-title">选择你想对比的方向（可多选）</view>
  <view
    class="direction-card {{selectedPaths.indexOf(item.type) >= 0 ? 'card-selected' : ''}}"
    wx:for="{{cards}}"
    wx:key="type"
    style="border-color: {{item.color}}; background: {{item.bgColor}}"
    data-type="{{item.type}}"
    bindtap="togglePathCard"
  >
    <view class="card-checkbox">
      <text wx:if="{{selectedPaths.indexOf(item.type) >= 0}}">&#x2705;</text>
      <text wx:else">○</text>
    </view>
    <view class="card-body">
      <view class="card-header">
        <text class="card-name">{{item.name}}</text>
        <text class="card-score" style="color: {{item.color}}">{{item.time_label}}</text>
      </view>
      <text class="card-insight">{{item.insight}}</text>
      <view class="card-meta">
        <text class="card-meta-item">⚠️ {{item.risk_label}}</text>
      </view>
    </view>
  </view>
  <button class="confirm-path-btn" bindtap="confirmPathSelection" wx:if="{{selectedPaths.length > 0}}">
    开始比对 (已选{{selectedPaths.length}}个方向)
  </button>
</view>

<!-- 内联方向卡片（沙盘完成后自动弹出）-->
<view wx:if="{{showCards && !selectingPaths}}" class="cards-section">
  <view class="cards-title">选择一个方向，开始深度规划</view>"""

content = content.replace(old_cards, new_cards)

with open(f"{frontend_base}/chatroom.wxml", "w", encoding="utf-8") as f:
    f.write(content)
print("chatroom.wxml updated with multi-select cards")

print("\nFrontend fixes done!")