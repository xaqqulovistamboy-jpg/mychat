from django.urls import re_path
from .consumers import ChatConsumer, NotifyConsumer

websocket_urlpatterns = [
    re_path(r"^ws/chat/general/$", ChatConsumer.as_asgi()),
    re_path(r"^ws/chat/u/(?P<username>[\w.@+-]+)/$", ChatConsumer.as_asgi()),
    re_path(r"^ws/notify/$", NotifyConsumer.as_asgi()),
]