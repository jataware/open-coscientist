import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# load environment variables from .env file
# looks for .env in mcp_server directory
env_path = Path(__file__).parent / '.env'

if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    logger.info(f"Loaded environment from {env_path}")
else:
    logger.warning(f".env file not found at {env_path} - using system environment only")

# logging config
LOG_LEVEL = os.environ.get('COSCIENTIST_MCP_LOG_LEVEL') or os.environ.get('LOG_LEVEL', 'INFO')
LOG_LEVEL = LOG_LEVEL.upper()
