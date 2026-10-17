from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from chat.views import chat_list, general_room, direct_room, signup, mark_read, upload_image
from chat.views import delete_message

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="chat/login.html"), name="login"),
    path("signup/", signup, name="signup"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", chat_list, name="chat_list"),
    path("chat/general/", general_room, name="general"),
    path("chat/u/<str:username>/", direct_room, name="direct"),
    path("chat/read/", mark_read, name="mark_read"),
    path("chat/upload/", upload_image, name="upload_image"),
    path("chat/delete/<int:message_id>/", delete_message, name="delete_message"),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)