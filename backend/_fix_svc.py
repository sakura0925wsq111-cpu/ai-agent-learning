import re

path = r"D:\ai-agent-learning\backend\services\growth_service.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Find the _RUNNING_LOOP / _ensure_loop section and class start
idx_loop = content.find("_RUNNING_LOOP")
idx_class = content.find("class GrowthService:", idx_loop)

# Find the old async bridge start (comment line above _RUNNING_LOOP)
idx_bridge = content.rfind("#", 0, idx_loop)
while idx_bridge > 0 and not content[idx_bridge:idx_loop].strip().startswith("#"):
    idx_bridge = content.rfind("#", 0, idx_bridge)

# Find the growth_service methods start (after __init__ and async methods)
idx_methods = content.find("    # \u2500\u2500 REST", idx_class)
if idx_methods < 0:
    idx_methods = content.find("    def start_session", idx_class)

new_bridge = """# \u2500\u2500 Persistent async bridge \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
# Single background event loop ensures AsyncSqliteSaver lock stays
# bound to the same loop across all invocations.

_BG_LOOP: "asyncio.AbstractEventLoop | None" = None


def _get_bg_loop() -> "asyncio.AbstractEventLoop":
    global _BG_LOOP
    if _BG_LOOP is None or _BG_LOOP.is_closed():
        _BG_LOOP = asyncio.new_event_loop()
        t = threading.Thread(target=_BG_LOOP.run_forever, daemon=True)
        t.start()
    return _BG_LOOP


def _run_async(coro, timeout: int = 60):
    loop = _get_bg_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


# \u2500\u2500 Service \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class GrowthService:

    def __init__(self, llm_service):
        self.llm = llm_service
        self.router = PlanningRouter(llm_service)
        self._graph = None

    async def _get_graph(self):
        if self._graph is None:
            self._graph = await build_growth_graph(self.llm, self.router)
        return self._graph

    async def _invoke(self, state, config):
        g = await self._get_graph()
        return await g.ainvoke(state, config)

    async def _stream(self, state, config):
        g = await self._get_graph()
        async for event in g.astream(state, config, stream_mode="updates"):
            yield event

"""

# Stitch: before_bridge + new_bridge + after_class_init
# Find where old methods start (after __init__)
old_methods_start = content.find("    # \u2500\u2500 REST API", idx_class)
if old_methods_start < 0:
    old_methods_start = content.find("    # \u2500\u2500 Public API", idx_class)
if old_methods_start < 0:
    old_methods_start = content.find("    def start_session", idx_class)

if idx_bridge < 0 or old_methods_start < 0:
    print(f"ERROR: idx_bridge={idx_bridge}, old_methods_start={old_methods_start}")
    exit(1)

content = content[:idx_bridge] + new_bridge + content[old_methods_start:]

# Add threading import if missing
if "import threading" not in content:
    content = content.replace(
        "import concurrent.futures",
        "import concurrent.futures\nimport threading",
    )

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("OK: growth_service.py rewritten")
