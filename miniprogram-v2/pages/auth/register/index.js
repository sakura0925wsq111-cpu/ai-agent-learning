const userService = require("../../../services/user-service");
const sessionStore = require("../../../stores/session-store");
const { showError } = require("../../../utils/page");

Page({
  data: { form: { student_id: "", name: "", password: "", school: "", college: "", major: "", enroll_year: "", grade: "" }, submitting: false },
  input(event) { this.setData({ [`form.${event.currentTarget.dataset.key}`]: event.detail.value }); },
  back() { wx.navigateBack(); },
  async submit() {
    const form = Object.assign({}, this.data.form);
    if (!form.student_id.trim() || !form.name.trim() || form.password.length < 6) { showError(null, "请填写学号、姓名和至少 6 位密码"); return; }
    this.setData({ submitting: true });
    try {
      const result = await userService.register(form);
      sessionStore.setSession(result);
      wx.reLaunch({ url: "/pages/onboarding/index" });
    } catch (error) { showError(error, "注册失败"); }
    finally { this.setData({ submitting: false }); }
  }
});
