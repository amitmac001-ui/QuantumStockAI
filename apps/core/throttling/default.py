from rest_framework.throttling import UserRateThrottle
from rest_framework.throttling import AnonRateThrottle


class BurstAnonThrottle(AnonRateThrottle):
    scope = "burst_anon"


class BurstUserThrottle(UserRateThrottle):
    scope = "burst_user"
