# Logging Guide

Open Coscientist uses Python's standard `logging` module. As a library, Open Coscientist does not configure logging output itself. Instead, developers using the library should configure logging in their application according to their needs.

## Quick Start

### Basic Package-Level Console Logging

```python

import logging

logging.basicConfig(
    level=logging.INFO, # For everything, or change as desired
    format="%(asctime)s %(message)s", # only show hour:minutes in this example.
    datefmt="%H:%M"
)
# For open_coscientist:
logging.getLogger("open_coscientist").setLevel(logging.DEBUG) # example, INFO or DEBUG
```

This is helpful and often times better that global logging config on the app in some instances.
For example, setting DEBUG level logging to all dependencies can become very verbose (other libs, say httpx, will also log at DEBUG level).

## Logging to Files

### Single File Logging

Write all logs to a single file:

```python
import logging
from pathlib import Path

# Create logs directory if it doesn't exist
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Configure file logging
logger = logging.getLogger("open_coscientist")
logger.setLevel(logging.DEBUG)

# Create file handler
file_handler = logging.FileHandler(log_dir / "coscientist.log")
file_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)
logger.addHandler(file_handler)

# Optional: also log to console
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter('%(levelname)s: %(message)s')
)
logger.addHandler(console_handler)
```

### Rotating File Logging

For long-running processes or multiple runs, use rotating logs to prevent unbounded file growth:

```python
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

log_dir = Path("logs") # example dir
log_dir.mkdir(exist_ok=True)

logger = logging.getLogger("open_coscientist")
logger.setLevel(logging.DEBUG)

# Rotating file handler - max 10MB per file, keep 5 backup files
rotating_handler = RotatingFileHandler(
    log_dir / "coscientist.log",
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5
)
rotating_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)
logger.addHandler(rotating_handler)
```

This creates files like:
```
logs/
├── coscientist.log        # Current log file
├── coscientist.log.1      # Previous log file
├── coscientist.log.2
├── coscientist.log.3
└── coscientist.log.4
```

### Time-Based Rotating Logs

Rotate logs daily or hourly:

```python
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logger = logging.getLogger("open_coscientist")
logger.setLevel(logging.DEBUG)

# Rotate daily, keep 30 days of logs
timed_handler = TimedRotatingFileHandler(
    log_dir / "coscientist.log",
    when="midnight",  # Options: 'S', 'M', 'H', 'D', 'midnight', 'W0'-'W6'
    interval=1,
    backupCount=30
)
timed_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)
logger.addHandler(timed_handler)
```

Rotation options:
- `when="S"` - seconds
- `when="M"` - minutes
- `when="H"` - hours
- `when="D"` - days
- `when="midnight"` - rotate at midnight
- `when="W0"` - rotate on Monday (W0-W6 for each day)

## Log Levels

Open Coscientist uses four log levels:

| Level | Purpose | When to Enable |
|-------|---------|----------------|
| `DEBUG` | Detailed diagnostics, cache hits/misses, internal state | Development, debugging |
| `INFO` | Progress updates, node completion, milestones | Production, normal usage |
| `WARNING` | Recoverable issues, fallbacks, missing optional features | Always recommended |
| `ERROR` | Failures that affect functionality | Always recommended |

## Filtering Logs by Module

Log only specific parts of Open Coscientist:

```python
import logging

# Only log from the generate node
logging.getLogger("open_coscientist.nodes.generate").setLevel(logging.DEBUG)

# Only log MCP client activity
logging.getLogger("open_coscientist.mcp_client").setLevel(logging.DEBUG)

# Silence everything else
logging.getLogger("open_coscientist").setLevel(logging.WARNING)
```

## Custom Log Format

Customize the log format for your needs:

```python
import logging

# Minimal format
formatter = logging.Formatter('%(levelname)s: %(message)s')

# Detailed format with function names
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(funcName)s:%(lineno)d - %(levelname)s - %(message)s'
)

# Include process/thread info for concurrent execution
formatter = logging.Formatter(
    '%(asctime)s [%(process)d:%(thread)d] %(name)s - %(levelname)s - %(message)s'
)

# JSON format for log aggregation tools
import json
class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            'timestamp': self.formatTime(record),
            'name': record.name,
            'level': record.levelname,
            'message': record.getMessage()
        })

handler.setFormatter(JsonFormatter())
```