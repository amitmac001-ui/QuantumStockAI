import json
import logging
from datetime import datetime


class JSONFormatter(logging.Formatter):

    def format(self, record):

        return json.dumps(
            {
                "time": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            },
            default=str,
        )
