Component({
  options: { multipleSlots: true },
  properties: { visible: { type: Boolean, value: false }, title: { type: String, value: "" }, submitLabel: { type: String, value: "" }, submitting: { type: Boolean, value: false }, destructive: { type: Boolean, value: false } },
  methods: { close() { if (!this.data.submitting) this.triggerEvent("close"); }, submit() { if (!this.data.submitting) this.triggerEvent("submit"); }, noop() {} }
});
