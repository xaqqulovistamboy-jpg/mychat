from django.db import models
from django.contrib.auth.models import User


class Message(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    recipient = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.CASCADE, related_name="received_messages",
    )
    text = models.TextField(blank=True)
    KIND_CHOICES = [
        ("text", "Matn"),
        ("image", "Rasm"),
        ("video", "Video"),
        ("audio", "Ovozli xabar"),
        ("video_note", "Dumaloq video"),
    ]
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default="text")
    file = models.FileField(upload_to="chat/%Y/%m/", blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created"]

    def __str__(self):
        return f"{self.user.username}: {self.text[:30]}"
class ChatRead(models.Model):
    """Foydalanuvchi har bir suhbatda qaysi xabargacha o'qiganini saqlaydi."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_reads")
    chat_key = models.CharField(max_length=64)  # "general" yoki "u<id>"
    last_read_id = models.BigIntegerField(default=0)

    class Meta:
        unique_together = ("user", "chat_key")    