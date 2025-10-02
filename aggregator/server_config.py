"""
Production server configuration for the aggregator service.
This file contains settings optimized for production use with Waitress.
"""

# Waitress server configuration
WAITRESS_CONFIG = {
    "host": "0.0.0.0",
    "port": 8888,
    "threads": 4,  # Number of threads to handle requests
    "connection_limit": 1000,  # Maximum number of simultaneous connections
    "cleanup_interval": 30,  # How often to clean up connections (seconds)
    "channel_timeout": 120,  # Channel timeout in seconds
    "max_request_body_size": 50741024,  # 50MB max request body size
    "expose_tracebacks": False,  # Don't expose tracebacks in production
    "asyncore_use_poll": True,  # Use poll() instead of select() for better performance
}

# Application configuration
APP_CONFIG = {
    "max_content_length": 10 * 1024 * 1024,  # 10MB max request size
    "json_sort_keys": False,  # Don't sort JSON keys for better performance
}

# Logging configuration for production
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        },
    },
    "handlers": {
        "default": {
            "level": "INFO",
            "formatter": "standard",
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False
        }
    }
}