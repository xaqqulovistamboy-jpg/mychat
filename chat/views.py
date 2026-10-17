from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import json

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import SignUpForm
from .models import ChatRead, Message


def serialize(messages, me, other_read_id=0):
    result = []
    for m in messages:
        local = timezone.localtime(m.created)
        result.append({
            "id": m.id,
            "user": m.user.username,
            "text": m.text,
            "time": local.strftime("%H:%M"),
            "date": local.strftime("%Y-%m-%d"),
                        "kind": m.kind,
            "url": m.file.url if m.file else None,
            # Mening xabarim qarshi tomon tomonidan o'qilganmi
            "read": m.user_id == me.id and m.id <= other_read_id,
        })
    return result


def _last_read(me, key):
    row = ChatRead.objects.filter(user=me, chat_key=key).first()
    return row.last_read_id if row else 0


def _set_read(me, key, latest_id):
    if not latest_id:
        return
    row, _ = ChatRead.objects.get_or_create(user=me, chat_key=key)
    if latest_id > row.last_read_id:
        row.last_read_id = latest_id
        row.save(update_fields=["last_read_id"])


def signup(request):
    if request.user.is_authenticated:
        return redirect("chat_list")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("chat_list")
    else:
        form = SignUpForm()

    return render(request, "chat/signup.html", {"form": form})


@login_required
def chat_list(request):
    me = request.user
    q = request.GET.get("q", "").strip()

    group_last = (
        Message.objects.filter(recipient__isnull=True)
        .select_related("user")
        .order_by("-created")
        .first()
    )

    general_unread = (
        Message.objects.filter(recipient__isnull=True, id__gt=_last_read(me, "general"))
        .exclude(user=me)
        .count()
    )

    # Xonadoshlar faqat shu chatda yozgan yoki uni ochgan odamlarga ko'rinadi
    has_general = (
        Message.objects.filter(recipient__isnull=True, user=me).exists()
        or ChatRead.objects.filter(user=me, chat_key="general").exists()
    )
    show_group = has_general or (len(q) >= 3 and q.lower() in "xonadoshlar")

    users = User.objects.exclude(id=me.id)
    if q:
        users = users.filter(username__icontains=q)

    chats = []
    for u in users.order_by("username"):
        last = (
            Message.objects.filter(Q(user=me, recipient=u) | Q(user=u, recipient=me))
            .order_by("-created")
            .first()
        )
        # Yozishmasi yo'q odamlar faqat qidiruvda ko'rinadi
        if last is None and not q:
            continue
        unread = Message.objects.filter(
            user=u, recipient=me, id__gt=_last_read(me, f"u{u.id}")
        ).count()
        chats.append({"user": u, "last": last, "unread": unread})

    chats.sort(
        key=lambda c: (c["last"] is None, -c["last"].created.timestamp() if c["last"] else 0)
    )
    return render(request, "chat/chat_list.html", {
        "q": q,
        "show_group": show_group,
        "group_last": group_last,
        "general_unread": general_unread,
        "chats": chats,
    })


@login_required
def general_room(request):
    last = list(
        Message.objects.filter(recipient__isnull=True)
        .select_related("user")
        .order_by("-created")[:50]
    )
    messages = list(reversed(last))
    if messages:
        _set_read(request.user, "general", max(m.id for m in messages))

    # Umumiy chatda boshqalar o'qigan eng so'nggi xabar
    other_read_id = (
        ChatRead.objects.filter(chat_key="general")
        .exclude(user=request.user)
        .aggregate(m=Max("last_read_id"))["m"] or 0
    )

    return render(request, "chat/room.html", {
        "history": serialize(messages, request.user, other_read_id),
        "me": request.user.username,
        "title": "Xonadoshlar",
        "is_group": True,
        "ws_path": "/ws/chat/general/",
    })


@login_required
def direct_room(request, username):
    me = request.user
    other = get_object_or_404(User, username=username)
    if other == me:
        return redirect("chat_list")

    last = list(
        Message.objects.filter(Q(user=me, recipient=other) | Q(user=other, recipient=me))
        .select_related("user")
        .order_by("-created")[:50]
    )
    messages = list(reversed(last))
    if messages:
        _set_read(me, f"u{other.id}", max(m.id for m in messages))

    # Qarshi tomon (other) men bilan bo'lgan suhbatni qayergacha o'qigan
    other_read_id = (
        ChatRead.objects.filter(user=other, chat_key=f"u{me.id}")
        .values_list("last_read_id", flat=True).first() or 0
    )

    return render(request, "chat/room.html", {
        "history": serialize(messages, me, other_read_id),
        "me": me.username,
        "title": other.username,
        "is_group": False,
        "ws_path": f"/ws/chat/u/{other.username}/",
    })


@login_required
@require_POST
def mark_read(request):
    try:
        chat = json.loads(request.body).get("chat", "")
    except (TypeError, ValueError, AttributeError):
        return JsonResponse({"ok": False}, status=400)

    me = request.user
    if chat == "general":
        key = "general"
        latest = (
            Message.objects.filter(recipient__isnull=True)
            .order_by("-id").values_list("id", flat=True).first()
        )
    elif chat.startswith("u:"):
        other = User.objects.filter(username=chat[2:]).first()
        if other is None:
            return JsonResponse({"ok": False}, status=404)
        key = f"u{other.id}"
        latest = (
            Message.objects.filter(Q(user=me, recipient=other) | Q(user=other, recipient=me))
            .order_by("-id").values_list("id", flat=True).first()
        )
    else:
        return JsonResponse({"ok": False}, status=400)

    _set_read(me, key, latest)
    return JsonResponse({"ok": True})
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_AUDIO_SIZE = 20 * 1024 * 1024
MAX_VIDEO_SIZE = 50 * 1024 * 1024


@login_required
@require_POST
def upload_image(request):
    f = request.FILES.get("file")
    chat = request.POST.get("chat", "")
    text = request.POST.get("text", "").strip()[:1000]
    me = request.user

    if f is None:
        return JsonResponse({"ok": False, "error": "Fayl tanlanmagan"}, status=400)

    # "video/webm;codecs=vp8" -> "video/webm"
    ctype = (f.content_type or "").split(";")[0].strip()

    if ctype in ALLOWED_IMAGE_TYPES:
        kind, limit, preview = "image", MAX_IMAGE_SIZE, "📷 Rasm"
    elif ctype.startswith("audio/"):
        kind, limit, preview = "audio", MAX_AUDIO_SIZE, "🎤 Ovozli xabar"
    elif ctype.startswith("video/"):
        if request.POST.get("kind") == "video_note":
            kind, limit, preview = "video_note", MAX_VIDEO_SIZE, "⭕ Dumaloq video"
        else:
            kind, limit, preview = "video", MAX_VIDEO_SIZE, "🎬 Video"
    else:
        return JsonResponse({"ok": False, "error": "Noto'g'ri fayl turi"}, status=400)

    if f.size > limit:
        return JsonResponse({"ok": False, "error": "Fayl juda katta"}, status=400)

    if chat == "general":
        recipient = None
    elif chat.startswith("u:"):
        recipient = User.objects.filter(username=chat[2:]).first()
        if recipient is None:
            return JsonResponse({"ok": False, "error": "Foydalanuvchi topilmadi"}, status=404)
    else:
        return JsonResponse({"ok": False, "error": "Noto'g'ri chat"}, status=400)

    msg = Message.objects.create(
        user=me,
        recipient=recipient,
        text=text,
        kind=kind,
        file=f,
    )

    local = timezone.localtime(msg.created)
    layer = get_channel_layer()

    if recipient is None:
        group = "general"
        notify_group = "notify_all"
        chat_key = "general"
    else:
        a, b = sorted([me.id, recipient.id])
        group = f"dm_{a}_{b}"
        notify_group = f"user_{recipient.id}"
        chat_key = f"u:{me.username}"

    async_to_sync(layer.group_send)(group, {
        "type": "chat.message",
        "id": msg.id,
        "user": me.username,
        "text": text,
        "time": local.strftime("%H:%M"),
        "date": local.strftime("%Y-%m-%d"),
        "kind": kind,
        "url": msg.file.url,
    })

    async_to_sync(layer.group_send)(notify_group, {
        "type": "notify.message",
        "sender_id": me.id,
        "sender": me.username,
        "chat": chat_key,
        "text": text[:120] or preview,
    })

    return JsonResponse({"ok": True, "id": msg.id, "url": msg.file.url})
@login_required
@require_POST
def delete_message(request, message_id):
    msg = get_object_or_404(Message, id=message_id)
    if msg.user_id != request.user.id:
        return JsonResponse({"ok": False, "error": "Ruxsat yo'q"}, status=403)

    if msg.recipient_id is None:
        group = "general"
    else:
        a, b = sorted([msg.user_id, msg.recipient_id])
        group = f"dm_{a}_{b}"

    deleted_id = msg.id
    if msg.file:
        msg.file.delete(save=False)
    msg.delete()

    async_to_sync(get_channel_layer().group_send)(group, {
        "type": "message.delete",
        "id": deleted_id,
    })
    return JsonResponse({"ok": True, "id": deleted_id})