from django.apps import AppConfig


class StoriesConfig(AppConfig):
    name = "apps.stories"
    label = "stories"

    def ready(self):
        from . import jobs  # noqa: F401  (navbat ishlovchilarini ro'yxatga oladi)
