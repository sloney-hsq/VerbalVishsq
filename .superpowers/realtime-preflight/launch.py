"""Local-only developer preflight; credentials never printed."""
import os
import sys
from pathlib import Path
from dotenv import dotenv_values
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

cfg = dotenv_values('.env', encoding='utf-8-sig', interpolate=False)
for name in ('QWEN_REALTIME_MODEL', 'QWEN_REALTIME_URL', 'QWEN_VOICE', 'NO_PROXY'):
    if cfg.get(name) is not None:
        os.environ[name] = cfg[name]
credentials = dotenv_values('C:/VerbalVis/backend/.env.example', encoding='utf-8-sig', interpolate=False)
os.environ['DASHSCOPE_API_KEY'] = credentials['DASHSCOPE_API_KEY'].strip()
os.environ['VERBALVIS_CONFIG'] = '.superpowers/realtime-preflight/config.json'
uvicorn.run('backend.main:app', host='127.0.0.1', port=8002, workers=1)
