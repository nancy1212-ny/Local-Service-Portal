from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("signup/", views.signup, name="signup"),
    path("requests/new/", views.create_request, name="create_request"),
    path("requests/<int:pk>/", views.request_detail, name="request_detail"),
    path("requests/<int:pk>/assign/", views.assign_request, name="assign_request"),
    path("requests/<int:pk>/status/", views.update_status, name="update_status"),
]
