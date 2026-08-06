import sys, os, time
os.chdir("D:/ai-agent-learning/backend")
sys.path.insert(0, ".")

t0 = time.time()
print("start")

from core.config import settings
from database.session import SessionLocal
from services.llm_service import LLMService
from services.growth_service import GrowthService
from schemas.growth import GrowthStartRequest
print("imports done {:.1f}s".format(time.time()-t0))

llm = LLMService()
service = GrowthService(llm)
db = SessionLocal()
uid = "dde545a6-b12e-41e2-a973-f02c7dbb1e58"
print("setup done {:.1f}s".format(time.time()-t0))

import asyncio
async def test():
    t1 = time.time()
    req = GrowthStartRequest(user_id=uid, agent="career")
    print("calling start_session at {:.1f}s".format(time.time()-t1))
    try:
        result = await asyncio.wait_for(service.start_session(db, request=req), timeout=90)
        print("OK {:.1f}s: sid={} msg={}".format(time.time()-t1, result.session_id, result.message[:80]))
    except asyncio.TimeoutError:
        print("TIMEOUT after {:.1f}s".format(time.time()-t1))
    except Exception as e:
        print("ERROR {:.1f}s: {}".format(time.time()-t1, e))
        import traceback; traceback.print_exc()
    finally:
        db.close()
        print("done")

asyncio.run(test())
