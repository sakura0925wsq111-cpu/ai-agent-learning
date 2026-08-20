Component({
  properties: { task: { type: Object, value: {} }, editable: { type: Boolean, value: true } },
  methods: {
    toggle() { if (this.data.editable && !this.data.task.cancelled) this.triggerEvent("toggle", this.data.task); },
    remove() { if (this.data.editable) this.triggerEvent("remove", this.data.task); }
  }
});
