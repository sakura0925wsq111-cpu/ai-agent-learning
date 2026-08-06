# iCampus 教师端 — 一个月核心开发计划 & 师生联动方案

> **文档日期**: 2026-08-06 | **开发周期**: 4 周（28 天）
> **原则**: MVP 优先，只做核心闭环，不铺功能
> **技术栈**: 后端 FastAPI（复用现有） + 前端 React SPA（新建 teacher-web）+ 学生端微信小程序（已有）

---

## 一、系统架构总览

### 1.1 三端关系

```
                     ┌──────────────────────┐
                     │    FastAPI 后端        │
                     │    (已有，增量开发)     │
                     │                        │
                     │  ┌──────────────────┐  │
                     │  │  /api/v1/teacher  │  │  ← [新增] 教师 API 路由组
                     │  │  auth / classes   │  │
                     │  │  assignments      │  │
                     │  │  exams / progress │  │
                     │  └────────┬─────────┘  │
                     │           │            │
                     │  ┌────────┴─────────┐  │
                     │  │   同步服务层       │  │  ← [新增] 发布→批量写入学生数据
                     │  └──┬──────────┬────┘  │
                     │     │          │       │
                     │  ┌──┴──┐  ┌───┴────┐  │
                     │  │学生  │  │ 学生    │  │  ← 现有 API（复用）
                     │  │API   │  │ Todo    │  │
                     │  └─────┘  └────────┘  │
                     └────┬──────┬──────┬────┘
                          │      │      │
              ┌───────────┘      │      └───────────┐
              ▼                  ▼                  ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  教师端 Web   │  │ 微信小程序    │  │  数据库 SQLite │
    │  (React SPA) │  │ (学生端，已有) │  │  (已有 + 3 新表)│
    └──────────────┘  └──────────────┘  └──────────────┘
```

### 1.2 开发顺序：层层递进

```
第1周  第2周         第3周              第4周
  │      │            │                  │
  ▼      ▼            ▼                  ▼
认证 ──→ 班级管理 ──→ 作业/考试发布 ──→ 完成度看板
登录     学生加入     联动同步            数据可视化
                             │
                             ▼
                      ┌─────────────┐
                      │  核心闭环完成  │
                      │  发布→同步→   │
                      │  完成→反馈    │
                      └─────────────┘
```

> 每一周都是下一周的前置条件，不可跳跃。第 3 周是核心价值周，前后端联动集中在这一周。

---

## 二、师生联动核心链路

### 2.1 联动数据流

```
教师端操作                      后端处理                       学生端结果
─────────                     ────────                      ──────────

[创建班级]
  POST /teacher/classes  ──→  写入 classes 表
                          ──→  生成 6 位班级码              ← [加入班级] 学生输入码
                                                              POST /class/enroll
                          ←──  写入 class_members 表

[发布作业]
  POST /teacher/          ──→  写入 teacher_assignments 表
  assignments             ──→  BackgroundTasks:
                               遍历班级学生，每人创建 1 条 Todo
                               (source='teacher',
                                assignment_id=...)
                                                             → 学生今日模式待办列表
                                                               出现"教师发布"标签的新待办

[学生完成作业]
                                                            → 勾选待办 ○→✓
                                                              POST /todos/{id}/toggle
                          ←──  Todo.status = 'done'

[教师查看完成度]
  GET /teacher/           ←──  COUNT(Todo WHERE status='done')
  assignments/{id}/              / COUNT(全班人数)
  submissions                  → 返回提交率 + 每人状态
```

### 2.2 同步策略

| 场景 | 策略 | 原因 |
|------|------|------|
| 教师**发布**作业/考试 | 即时批量写入 | 学生需要立刻看到，不能延迟 |
| 教师**编辑**作业 | 级联删除旧 Todo → 重建 | 避免过期数据，保持一致性 |
| 教师**删除**作业 | 级联删除所有学生 Todo | 清理垃圾数据 |
| **新学生**加入班级 | 不回溯历史 | 简化逻辑，一个月不做增量同步 |
| 学生**完成**待办 | 即时更新 status | 已有接口直接复用 |

### 2.3 数据模型变更

#### 新增表（3 张）

```
classes                     class_members               teacher_assignments
────────────                ─────────────               ───────────────────
id (PK)                     id (PK)                     id (PK)
teacher_id → users.id       class_id → classes.id       class_id → classes.id
name                         student_id → users.id       teacher_id → users.id
course_name                  role (student/teacher)      title
semester                     joined_at                   description
class_code (UNIQUE, 6位)                                 deadline
created_at                  UNIQUE(class_id,student_id)  attachment
updated_at                                               created_at / updated_at
```

#### 现有表微调

```
users:       + role VARCHAR(20) DEFAULT 'student'    -- 'student' / 'teacher'
todos:       + class_id → classes.id                 -- 来源班级
             + assignment_id → teacher_assignments.id -- 来源作业模板
exams:       + class_id → classes.id                 -- 来源班级
```

---

## 三、四周开发计划（前后端分离）

---

### 第 1 周：基础架构 + 认证登录

> **本周目标**: 教师能注册、登录，进入空白管理面板。前后端骨架立起来。

#### 依赖链

```
后端: users 表加 role → 注册接口 → 登录接口 → JWT 路由守卫
前端: 项目脚手架 → 登录页 UI → 调通登录 API → 路由守卫
联调: 注册 → 登录 → 获得 token → 访问受保护页面
```

#### 后端任务

| # | 任务 | 文件 | 估时 | 前置 |
|---|------|------|:--:|---|
| B1.1 | `users` 表新增 `role` 字段（student/teacher），数据库迁移 | `models/user.py` + migration 脚本 | 2h | — |
| B1.2 | 教师注册接口 `POST /api/v1/teacher/register` — 邮箱+密码，role 自动设为 teacher，返回 JWT | `app/api/v1/teacher/auth.py` | 3h | B1.1 |
| B1.3 | 教师登录接口 `POST /api/v1/teacher/login` — 验证密码，返回 JWT | `app/api/v1/teacher/auth.py` | 2h | B1.1 |
| B1.4 | 教师信息接口 `GET /api/v1/teacher/me` — 需 JWT，返回当前教师信息 | `app/api/v1/teacher/auth.py` | 1h | B1.3 |
| B1.5 | 创建 `teacher` 路由组，挂载到 `app/main.py` | `app/api/v1/teacher/__init__.py`, `router.py` | 1h | B1.2 |
| B1.6 | JWT 依赖注入：解析 token 并校验 teacher 角色 | `utils/auth.py`（扩展现有） | 2h | B1.3 |

**后端周产出**: 三个认证接口可用 + teacher 路由组就绪

#### 前端任务

| # | 任务 | 文件/目录 | 估时 | 前置 |
|---|------|-----------|:--:|---|
| F1.1 | 项目初始化：Vite + React + TypeScript + Ant Design | `teacher-web/` | 2h | — |
| F1.2 | Axios 封装：baseURL、拦截器、token 注入、401 处理 | `teacher-web/src/api/` | 2h | F1.1 |
| F1.3 | 登录页 UI：邮箱+密码表单 + "注册"和"登录"Tab 切换 | `teacher-web/src/pages/Login.tsx` | 3h | F1.1 |
| F1.4 | 注册页逻辑：调用 `POST /teacher/register`，成功后跳转登录 | 同上 | 1h | F1.3, B1.2 |
| F1.5 | 登录逻辑：调用 `POST /teacher/login`，存 token 到 localStorage | 同上 | 1h | F1.3, B1.3 |
| F1.6 | 路由守卫组件：无 token → 跳转 `/login` | `teacher-web/src/components/AuthGuard.tsx` | 1h | F1.2 |
| F1.7 | 空壳首页：登录后展示"欢迎，XX 老师" + 侧边栏骨架 | `teacher-web/src/pages/Dashboard.tsx` | 2h | F1.6 |
| F1.8 | 路由配置：`/login` `/dashboard` `/classes` 等 | `teacher-web/src/App.tsx` | 1h | F1.7 |

**前端周产出**: 登录注册流程跑通，进入空壳管理面板

#### 联调检查点（Day 7）

- [ ] 教师注册 → 数据库 users 表有 role=teacher 的记录
- [ ] 教师登录 → 返回 JWT → 前端存 token → 跳转 Dashboard
- [ ] 无 token 访问 `/dashboard` → 自动跳转 `/login`
- [ ] token 过期 → API 返回 401 → 前端跳转登录页

---

### 第 2 周：班级管理 + 学生加入

> **本周目标**: 教师创建班级 → 生成邀请码 → 学生在小程序输入码加入 → 教师看到成员列表。打通师生双向连接。

#### 依赖链

```
后端: 班级表+成员表 → 班级CRUD → 邀请码生成 → 学生加入班级 → 成员列表
前端: 班级列表页 → 创建班级弹窗 → 班级详情(成员+邀请码)
小程序: 新增"加入班级"页面 → 输入班级码 → 调加入接口
联调: 创建班级 → 学生加入 → 教师看到成员
```

#### 后端任务

| # | 任务 | 文件 | 估时 | 前置 |
|---|------|------|:--:|---|
| B2.1 | 新增 ORM：`Class`、`ClassMember`、`TeacherAssignment` 三张表 | `models/teacher.py` | 2h | B1.1 |
| B2.2 | 创建班级 `POST /api/v1/teacher/classes` — 自动生成 6 位唯一邀请码 | `app/api/v1/teacher/classes.py` | 2h | B2.1 |
| B2.3 | 班级列表 `GET /api/v1/teacher/classes` — 当前教师的所有班级 | 同上 | 1h | B2.2 |
| B2.4 | 班级详情 `GET /api/v1/teacher/classes/{id}` + 编辑 `PUT` + 删除 `DELETE` | 同上 | 2h | B2.2 |
| B2.5 | 班级成员列表 `GET /api/v1/teacher/classes/{id}/members` | 同上 | 1h | B2.3 |
| B2.6 | 学生加入班级 `POST /api/v1/class/enroll` — 输入班级码，校验唯一性，写入 class_members | `app/api/v1/teacher/classes.py` | 2h | B2.1 |
| B2.7 | 我的班级列表（学生视角）`GET /api/v1/class/my-classes` | 同上 | 1h | B2.6 |

**后端周产出**: 班级全生命周期 CRUD + 学生加入退出

#### 前端任务（教师 Web 端）

| # | 任务 | 文件 | 估时 | 前置 |
|---|------|------|:--:|---|
| F2.1 | 班级列表页：表格展示（班名/课程/人数/学期）+ 新建按钮 | `teacher-web/src/pages/Classes.tsx` | 3h | F1.8, B2.3 |
| F2.2 | 创建班级弹窗：表单（班名/课程名/学期），提交后刷新列表 | 同上 | 2h | F2.1, B2.2 |
| F2.3 | 班级详情页：Tab 切换（基本信息 + 成员列表 + 邀请码展示） | `teacher-web/src/pages/ClassDetail.tsx` | 3h | F2.1, B2.4 |
| F2.4 | 成员列表：头像+姓名+学号+加入时间 | 同上 | 1h | F2.3, B2.5 |
| F2.5 | 邀请码展示区：大字号展示 + 复制按钮 + "分享到微信群"提示 | 同上 | 1h | F2.3 |

**前端周产出**: 教师端班级管理面板完成

#### 前端任务（学生端小程序，改动最小化）

| # | 任务 | 文件 | 估时 | 前置 |
|---|------|------|:--:|---|
| F2.6 | 新增"加入班级"页面：输入框 + 提交按钮 | `pages/join-class/` | 2h | — |
| F2.7 | 调 `POST /api/v1/class/enroll`，成功提示 + 跳转 | 同上 | 1h | F2.6, B2.6 |
| F2.8 | 在"我的"页面添加入口："我的班级"列表 | `pages/mine/` | 1h | B2.7 |

**小程序周产出**: 学生能扫码或手动输入加入班级

#### 联调检查点（Day 14）

- [ ] 教师创建班级 → 数据库有 classes 记录 → 邀请码唯一
- [ ] 学生在小程序输入邀请码 → 加入成功 → class_members 有记录
- [ ] 教师端成员列表实时显示新加入学生
- [ ] 同一学生重复加入 → 409 冲突提示
- [ ] 班级码不存在 → 404 提示

---

### 第 3 周：作业/考试发布 + 联动同步（核心周）

> **本周目标**: 实现核心联动闭环 —— 教师发布作业 → 全班学生 Todo 自动生成 → 学生完成 → 状态回传。

#### 依赖链

```
后端: 教师作业CRUD → 批量同步服务 → Todo批量生成 → 教师考试CRUD → 考试批量生成
前端: 作业管理页(选班级→填表单→发布) → 考试管理页
小程序: 待办列表适配"教师发布"标签 → 考试时间轴适配
联调: 发布→学生端出现→完成→后端状态变更
```

#### 后端任务

| # | 任务 | 文件 | 估时 | 前置 |
|---|------|------|:--:|---|
| B3.1 | 发布作业 `POST /api/v1/teacher/assignments` — 创建作业模板 + BackgroundTasks 批量生成每学生 1 条 Todo | `app/api/v1/teacher/assignments.py` | 5h | B2.1 |
| B3.2 | 作业列表 `GET /api/v1/teacher/assignments` — 按班级筛选，包含已完成/总人数统计 | 同上 | 2h | B3.1 |
| B3.3 | 作业详情 `GET` + 编辑 `PUT` + 删除 `DELETE` — 编辑时级联重建 Todo，删除时级联清理 | 同上 | 3h | B3.1 |
| B3.4 | 发布考试 `POST /api/v1/teacher/exams` — 为全班学生各创建 1 条 Exam（source=teacher） | `app/api/v1/teacher/exams.py` | 3h | B2.1 |
| B3.5 | 考试列表 `GET` + 详情 `GET` + 编辑 `PUT` + 删除 `DELETE` | 同上 | 2h | B3.4 |
| B3.6 | `todos` 表 + `exams` 表新增 `class_id`、`assignment_id` 字段迁移 | migration 脚本 | 1h | B1.1 |
| B3.7 | 同步服务封装：`sync_service.py` — publish_to_class() / revoke_from_class() | `services/sync_service.py` | 2h | B3.1 |

**后端周产出**: 发布→同步→状态变更 完整 API 链路

#### 前端任务（教师 Web 端）

| # | 任务 | 文件 | 估时 | 前置 |
|---|------|------|:--:|---|
| F3.1 | 作业管理页：班级选择器 + 作业列表表格 + "发布作业"按钮 | `teacher-web/src/pages/Assignments.tsx` | 3h | F2.1, B3.2 |
| F3.2 | 发布作业弹窗：选择目标班级 → 标题/描述/截止时间/附件 → 提交 | 同上 | 2h | F3.1, B3.1 |
| F3.3 | 作业详情页：展示内容 + 编辑按钮 + 删除确认 | 同上 | 2h | F3.1, B3.3 |
| F3.4 | 考试管理页：类似作业管理，字段不同（科目/日期/时间/地点） | `teacher-web/src/pages/Exams.tsx` | 3h | F2.1, B3.5 |
| F3.5 | 删除确认弹窗："删除后所有学生的待办也将清除"警告 | 通用组件 | 1h | F3.3 |

**前端周产出**: 教师端作业+考试完整管理面板

#### 前端任务（学生端小程序适配）

| # | 任务 | 文件 | 估时 | 前置 |
|---|------|------|:--:|---|
| F3.6 | 待办列表适配：`source=teacher` 的 Todo 显示"教师发布"标签 + 显示所属课程 | `pages/index/` | 2h | B3.1 |
| F3.7 | 考试时间轴适配：`source=teacher` 的 Exam 显示"教师发布"标签 | `pages/schedule/` | 1h | B3.4 |

**小程序周产出**: 教师发布的内容在学生端有明显标识

#### 联调检查点（Day 21）⭐ 核心闭环

- [ ] 教师选班级 → 填作业信息 → 点发布 → 数据库产生 N 条 Todo（N=班级人数）
- [ ] 学生打开小程序 → 首页待办列表出现"教师发布 · 高等数学"标签的新待办
- [ ] 学生勾选完成待办 → Todo.status = done
- [ ] 教师编辑作业标题 → 学生旧 Todo 删除 → 新 Todo 生成（截止时间不变）
- [ ] 教师删除作业 → 所有学生该作业的 Todo 级联删除
- [ ] 教师发布考试 → 学生时间轴出现考试事件

---

### 第 4 周：完成度看板 + 全链路收尾

> **本周目标**: 教师端能直观看到班级作业完成率、每个学生的提交状态。全链路联调 + 部署。

#### 依赖链

```
后端: 完成度聚合查询 → 提交详情查询 → 学生个人进度
前端: 看板仪表盘 → 提交详情表格 → 布局打磨
联调: 全班联调 → Bug修复 → 部署
```

#### 后端任务

| # | 任务 | 文件 | 估时 | 前置 |
|---|------|------|:--:|---|
| B4.1 | 班级完成度概览 `GET /api/v1/teacher/classes/{id}/progress` — 返回每个作业的提交率 + 考试列表 | `app/api/v1/teacher/progress.py` | 3h | B3.1, B3.4 |
| B4.2 | 单个作业提交详情 `GET /api/v1/teacher/assignments/{id}/submissions` — 每人姓名+状态+完成时间 | 同上 | 2h | B3.1 |
| B4.3 | 单个学生进度 `GET /api/v1/teacher/classes/{id}/students/{sid}/progress` — 该生的所有作业完成情况 | 同上 | 2h | B4.2 |

**后端周产出**: 三个聚合查询接口，数据看板后端就绪

#### 前端任务（教师 Web 端）

| # | 任务 | 文件 | 估时 | 前置 |
|---|------|------|:--:|---|
| F4.1 | 班级看板页：每个作业一行 → 进度条（完成/总数） + 考试倒计时卡片 | `teacher-web/src/pages/ClassProgress.tsx` | 4h | F3.1, B4.1 |
| F4.2 | 提交详情页：表格（学号/姓名/状态/完成时间/操作）→ 点击作业行进入 | `teacher-web/src/pages/AssignmentSubmissions.tsx` | 3h | F4.1, B4.2 |
| F4.3 | 侧边栏导航完善：班级列表 / 作业管理 / 考试管理 / 退出登录 | `teacher-web/src/components/Sidebar.tsx` | 2h | F2.1 |
| F4.4 | 全局 UI 打磨：加载态（Spin）、空状态（Empty）、错误提示（message） | 全局 | 3h | 所有前端页面 |

**前端周产出**: 教师端 MVP 完整可用

#### 联调 & 收尾

| # | 任务 | 估时 | 前置 |
|---|------|:--:|---|
| T4.1 | 全链路端到端测试：创建班级→学生加入→发布作业→学生完成→看板刷新 | 4h | 全部 |
| T4.2 | 边界情况修复：空班级发布、删除有学生的班级、并发加入、超长文本 | 3h | T4.1 |
| T4.3 | 教师端打包部署：`npm run build` → Nginx 静态托管，API 同域代理 | 2h | T4.1 |
| T4.4 | 小程序端回归测试：确保新改动不影响现有功能 | 2h | T4.1 |

#### 联调检查点（Day 28）

- [ ] 教师发布 2 个作业到 5 人班级 → 看板显示 2 行进度条
- [ ] 3 人完成 → 进度条 60% → 点进去看到完成的 3 人 + 未完成的 2 人
- [ ] 教师发布考试 → 看板显示考试倒计时卡片
- [ ] 新学生中途加入班级 → 已有作业不出现在其待办（不回填历史）
- [ ] 教师端部署后可公网访问，小程序正常联动

---

## 四、API 接口总表

### 教师认证

| 方法 | 路径 | 说明 | Auth |
|------|------|------|:--:|
| POST | `/api/v1/teacher/register` | 教师注册 | — |
| POST | `/api/v1/teacher/login` | 教师登录 → JWT | — |
| GET | `/api/v1/teacher/me` | 当前教师信息 | Teacher |

### 班级管理

| 方法 | 路径 | 说明 | Auth |
|------|------|------|:--:|
| POST | `/api/v1/teacher/classes` | 创建班级 | Teacher |
| GET | `/api/v1/teacher/classes` | 我的班级列表 | Teacher |
| GET | `/api/v1/teacher/classes/{id}` | 班级详情 | Teacher |
| PUT | `/api/v1/teacher/classes/{id}` | 编辑班级 | Teacher |
| DELETE | `/api/v1/teacher/classes/{id}` | 删除班级 | Teacher |
| GET | `/api/v1/teacher/classes/{id}/members` | 班级成员列表 | Teacher |

### 班级加入（学生端）

| 方法 | 路径 | 说明 | Auth |
|------|------|------|:--:|
| POST | `/api/v1/class/enroll` | 输入班级码加入 | Student |
| GET | `/api/v1/class/my-classes` | 我加入的班级 | Student |

### 作业管理

| 方法 | 路径 | 说明 | Auth |
|------|------|------|:--:|
| POST | `/api/v1/teacher/assignments` | 发布作业 → 批量生成 Todo | Teacher |
| GET | `/api/v1/teacher/assignments` | 作业列表（按班级筛选） | Teacher |
| GET | `/api/v1/teacher/assignments/{id}` | 作业详情 | Teacher |
| PUT | `/api/v1/teacher/assignments/{id}` | 编辑作业 → 级联重建 Todo | Teacher |
| DELETE | `/api/v1/teacher/assignments/{id}` | 删除作业 → 级联删除 Todo | Teacher |
| GET | `/api/v1/teacher/assignments/{id}/submissions` | 学生提交详情 | Teacher |

### 考试管理

| 方法 | 路径 | 说明 | Auth |
|------|------|------|:--:|
| POST | `/api/v1/teacher/exams` | 发布考试 → 批量生成 Exam | Teacher |
| GET | `/api/v1/teacher/exams` | 考试列表 | Teacher |
| GET | `/api/v1/teacher/exams/{id}` | 考试详情 | Teacher |
| PUT | `/api/v1/teacher/exams/{id}` | 编辑考试 | Teacher |
| DELETE | `/api/v1/teacher/exams/{id}` | 删除考试 → 级联删除 Exam | Teacher |

### 完成度看板

| 方法 | 路径 | 说明 | Auth |
|------|------|------|:--:|
| GET | `/api/v1/teacher/classes/{id}/progress` | 班级完成度概览 | Teacher |
| GET | `/api/v1/teacher/classes/{id}/students/{sid}/progress` | 单个学生进度 | Teacher |

---

## 五、不做清单（防止范围蔓延）

| 不做 | 原因 | 后期计划 |
|------|------|---------|
| 课程表发布同步 | 到学生端的解析逻辑复杂，1 个月做不完 | 第 2 阶段 |
| 在线批改/打分 | 需要附件查看器+批注系统，工程量太大 | 第 2 阶段 |
| 班级公告/通知 | 非核心闭环，可微信群里替代 | 第 2 阶段 |
| 消息推送（模板消息） | 微信审核周期长，且需额外开发 | 第 3 阶段 |
| 数据导出（Excel） | 非 MVP 必需 | 第 2 阶段 |
| 多教师协作 | 权限模型复杂 | 第 3 阶段 |
| 教师端 AI 功能 | 与当前 AI 系统耦合度高 | 第 3 阶段 |
| 文件批量上传 | 作业附件单个上传够用 | 第 2 阶段 |

---

> 📄 文档版本：v2.0 | 日期：2026-08-06
