import sys
sys.path.insert(0, r'D:\ai-agent-learning\venv\Lib\site-packages')
sys.path.insert(0, r'D:\ai-agent-learning\backend')
from app.main import app
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=8000, log_level='warning')
