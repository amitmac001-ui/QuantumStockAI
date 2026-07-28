from django.core.cache import cache


class CacheManager:

    @staticmethod
    def get(key):
        return cache.get(key)

    @staticmethod
    def set(key, value, timeout=300):
        cache.set(key, value, timeout)

    @staticmethod
    def delete(key):
        cache.delete(key)

    @staticmethod
    def clear():
        cache.clear()

    @staticmethod
    def remember(key, callback, timeout=300):

        data = cache.get(key)

        if data is not None:
            return data

        data = callback()

        cache.set(key, data, timeout)

        return data
