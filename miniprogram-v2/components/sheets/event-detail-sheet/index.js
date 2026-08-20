Component({ properties: { visible: Boolean, event: Object }, methods: { close() { this.triggerEvent("close"); } } });
