Component({
  properties: { phases: { type: Array, value: [] }, currentKey: { type: String, value: "" }, syncedKeys: { type: Array, value: [] } },
  data: { viewPhases: [] },
  observers: {
    "phases,syncedKeys": function update(phases, syncedKeys) {
      const synced = syncedKeys || [];
      this.setData({ viewPhases: (phases || []).map((item) => Object.assign({}, item, { synced: Boolean(item.synced || synced.indexOf(item.key) >= 0) })) });
    }
  },
  methods: { select(event) { this.triggerEvent("select", event.currentTarget.dataset.phase); } }
});
