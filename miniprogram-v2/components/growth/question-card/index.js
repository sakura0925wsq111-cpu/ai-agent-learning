Component({
  properties: { question: { type: Object, value: {} }, disabled: { type: Boolean, value: false } },
  methods: { choose(event) { if (!this.data.disabled) this.triggerEvent("answer", { value: event.currentTarget.dataset.value }); } }
});
