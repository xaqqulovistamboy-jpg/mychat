import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from .models import ChatRead, Message


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close()
            return

        username = self.scope["url_route"]["kwargs"].get("username")
        if username is None:
            # Umumiy guruh chat
            self.recipient = None
            self.group = "general"
        else:
            # Shaxsiy (1-ga-1) chat
            other = await self.get_user(username)
            if other is None or other.id == user.id:
                await self.close()
                return
            self.recipient = other
            a, b = sorted([user.id, other.id])
            self.group = f"dm_{a}_{b}"

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (TypeError, ValueError):
            return
        if not isinstance(data, dict):
            return

        # O'qilganlik: foydalanuvchi suhbatni ko'rayotgan bo'lsa
        if data.get("type") == "read":
            last_id = await self.mark_read_db()
            if last_id:
                await self.channel_layer.group_send(self.group, {
                    "type": "read.update",
                    "reader": self.scope["user"].username,
                    "last_id": last_id,
                })
            return

        text = str(data.get("text", "")).strip()[:1000]
        if not text:
            return

        msg = await self.save_message(text)
        local = timezone.localtime(msg.created)
        sender = self.scope["user"].username

        # Suhbatdagilarga xabar
        await self.channel_layer.group_send(self.group, {
            "type": "chat.message",
            "id": msg.id,
            "user": sender,
            "text": text,
            "time": local.strftime("%H:%M"),
            "date": local.strftime("%Y-%m-%d"),
        })

        # Bildirishnoma
        if self.recipient is None:
            await self.channel_layer.group_send("notify_all", {
                "type": "notify.message",
                "sender_id": self.scope["user"].id,
                "sender": sender,
                "chat": "general",
                "text": text[:120],
            })
        else:
            await self.channel_layer.group_send(f"user_{self.recipient.id}", {
                "type": "notify.message",
                "sender_id": self.scope["user"].id,
                "sender": sender,
                "chat": f"u:{sender}",
                "text": text[:120],
            })

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "id": event["id"],
            "user": event["user"],
            "text": event["text"],
            "time": event["time"],
            "date": event["date"],
            "kind": event.get("kind", "text"),
            "url": event.get("url"),
        }))
    async def message_delete(self, event):
        await self.send(text_data=json.dumps({"type": "delete", "id": event["id"]}))    

    async def read_update(self, event):
        # O'zi o'qiganda o'ziga belgi kerak emas
        if event["reader"] == self.scope["user"].username:
            return
        await self.send(text_data=json.dumps({
            "type": "read",
            "last_id": event["last_id"],
        }))

    @database_sync_to_async
    def get_user(self, username):
        return User.objects.filter(username=username).first()

    @database_sync_to_async
    def save_message(self, text):
        return Message.objects.create(
            user=self.scope["user"], recipient=self.recipient, text=text
        )

    @database_sync_to_async
    def mark_read_db(self):
        me = self.scope["user"]
        if self.recipient is None:
            key = "general"
            latest = (
                Message.objects.filter(recipient__isnull=True)
                .order_by("-id").values_list("id", flat=True).first()
            )
        else:
            key = f"u{self.recipient.id}"
            latest = (
                Message.objects.filter(
                    Q(user=me, recipient=self.recipient) | Q(user=self.recipient, recipient=me)
                )
                .order_by("-id").values_list("id", flat=True).first()
            )
        if not latest:
            return 0
        row, _ = ChatRead.objects.get_or_create(user=me, chat_key=key)
        if latest > row.last_read_id:
            row.last_read_id = latest
            row.save(update_fields=["last_read_id"])
        return latest


class NotifyConsumer(AsyncWebsocketConsumer):
    """Har bir foydalanuvchi uchun bildirishnoma kanali."""

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close()
            return

        self.groups_joined = [f"user_{user.id}", "notify_all"]
        for group in self.groups_joined:
            await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        for group in getattr(self, "groups_joined", []):
            await self.channel_layer.group_discard(group, self.channel_name)

    async def notify_message(self, event):
        if event["sender_id"] == self.scope["user"].id:
            return
        await self.send(text_data=json.dumps({
            "chat": event["chat"],
            "sender": event["sender"],
            "text": event["text"],
        }))