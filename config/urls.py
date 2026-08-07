from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('portal.urls')), # Portal के URLs को यहाँ जोड़ दिया
]

# 🚀 NEW: Media फाइल्स (इमेजेज) को लोकल सर्वर पर लोड करने के लिए
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)