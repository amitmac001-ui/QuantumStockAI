from django.db import models


class BaseRepository:

    model: models.Model = None

    @classmethod
    def all(cls):
        return cls.model.objects.all()

    @classmethod
    def filter(cls, **kwargs):
        return cls.model.objects.filter(**kwargs)

    @classmethod
    def get(cls, **kwargs):
        return cls.model.objects.get(**kwargs)

    @classmethod
    def first(cls, **kwargs):
        return cls.model.objects.filter(**kwargs).first()

    @classmethod
    def exists(cls, **kwargs):
        return cls.model.objects.filter(**kwargs).exists()

    @classmethod
    def create(cls, **kwargs):
        return cls.model.objects.create(**kwargs)

    @classmethod
    def update(cls, queryset, **kwargs):
        return queryset.update(**kwargs)

    @classmethod
    def delete(cls, queryset):
        return queryset.delete()

    @classmethod
    def bulk_create(cls, objects):
        return cls.model.objects.bulk_create(objects)

    @classmethod
    def bulk_update(cls, objects, fields):
        return cls.model.objects.bulk_update(
            objects,
            fields,
        )
