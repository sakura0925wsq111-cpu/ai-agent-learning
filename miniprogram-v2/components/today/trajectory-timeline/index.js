Component({
  properties: { events: { type: Array, value: [] } },
  data: { viewEvents: [] },
  observers: {
    events(events) {
      this.setData({ viewEvents: (events || []).map((item, index) => Object.assign({}, item, { isNext: index === 0 })) });
    }
  },
  methods: { select(event) { this.triggerEvent("select", event.currentTarget.dataset.item); } }
});
