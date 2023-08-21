import redis
import sys
from packages.common.storage import Storage
from packages.common.constants import (
    REDIS_HOSTNAME,
    REDIS_PORT,
    REDIS_PASSWORD,
)
from packages.common.constants import (
    DEVELOPMENT_ENVIRONMENTS,
    APP_ENV,
)

def init():
    global redis_cts

    if APP_ENV not in DEVELOPMENT_ENVIRONMENTS:
        redis_cts = RedisCts()
        try:
            redis_cts.connection.ping()
        except:
            Storage.store_exception(sys.exc_info())
            redis_cts = False
    else:
        redis_cts = False


class RedisCts:

    connection = None

    def __init__(self):
        self.connection = redis.StrictRedis(
            host=REDIS_HOSTNAME,
            port=REDIS_PORT,
            ssl=True,
            password=REDIS_PASSWORD,
            socket_timeout=5,
            ssl_cert_reqs=None,
        )
