from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('portal.urls')), # Portal के URLs को यहाँ जोड़ दिया
]