const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    name: "",
    studentId: "",
    school: "",
    college: "",
    major: "",
    enrollYear: "",
    grade: "",
    password: "",
    agreed: false,
    canSubmit: false
  },

  onLoad(options) {
    const info = wx.getSystemInfoSync();
    this.setData({ statusBarHeight: info.statusBarHeight });
  },

  onNameInput(e) { this.setData({ name: e.detail.value }); this.checkCanSubmit(); },
  onStudentIdInput(e) { this.setData({ studentId: e.detail.value }); this.checkCanSubmit(); },
  onSchoolInput(e) { this.setData({ school: e.detail.value }); this.checkCanSubmit(); },
  onCollegeInput(e) { this.setData({ college: e.detail.value }); this.checkCanSubmit(); },
  onMajorInput(e) { this.setData({ major: e.detail.value }); this.checkCanSubmit(); },
  onPasswordInput(e) { this.setData({ password: e.detail.value }); this.checkCanSubmit(); },

  checkCanSubmit() {
    const { name, studentId, school, college, major, enrollYear, grade, password, agreed } = this.data;
    this.setData({
      canSubmit: !!(name && studentId && school && college && major && enrollYear && grade && password.length >= 6 && agreed)
    });
  },

  toggleAgree() {
    this.setData({ agreed: !this.data.agreed });
    this.checkCanSubmit();
  },

  selectYear() {
    const that = this;
    wx.showActionSheet({
      itemList: ["2020", "2021", "2022", "2023", "2024", "2025"],
      success(res) {
        const years = ["2020", "2021", "2022", "2023", "2024", "2025"];
        that.setData({ enrollYear: years[res.tapIndex] });
        that.checkCanSubmit();
      }
    });
  },

  selectGrade() {
    const that = this;
    // 先选择学历层次（6项以内）
    wx.showActionSheet({
      itemList: ["本科", "硕士研究生"],
      success(res) {
        if (res.tapIndex === 0) {
          // 本科
          wx.showActionSheet({
            itemList: ["大一", "大二", "大三", "大四"],
            success(r) {
              const grades = ["大一", "大二", "大三", "大四"];
              that.setData({ grade: grades[r.tapIndex] });
              that.checkCanSubmit();
            }
          });
        } else {
          // 硕士研究生
          wx.showActionSheet({
            itemList: ["研一", "研二", "研三"],
            success(r) {
              const grades = ["研一", "研二", "研三"];
              that.setData({ grade: grades[r.tapIndex] });
              that.checkCanSubmit();
            }
          });
        }
      }
    });
  },

  async doRegister() {
    if (!this.data.canSubmit) return;
    wx.showLoading({ title: "注册中..." });

    try {
      const res = await app.request({
        url: "/api/v1/users",
        method: "POST",
        data: {
          student_id: this.data.studentId,
          name: this.data.name,
          password: this.data.password,
          school: this.data.school,
          college: this.data.college,
          major: this.data.major,
          enroll_year: this.data.enrollYear,
          grade: this.data.grade
        }
      });
      app.setAuth(res.token, res.user_id, res.user);
      wx.switchTab({ url: "/pages/index/index" });
    } catch (err) {
      wx.showToast({ title: err.message || "注册失败", icon: "none" });
    } finally {
      wx.hideLoading();
    }
  },

  goBack() { wx.navigateBack(); },
  showAgreement() { wx.navigateTo({ url: "/pages/agreement/agreement?type=user" }); },
  showPrivacy() { wx.navigateTo({ url: "/pages/agreement/agreement?type=privacy" }); }
});