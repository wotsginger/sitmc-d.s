import logging
from waitress import serve
from app import app

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

serve(app, host='0.0.0.0', port=30500)
