from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ServiceRequest, StatusHistory, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Portal", {"fields": ("role", "phone", "skill")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Portal", {"fields": ("role", "phone", "skill")}),)
    list_display = ("username", "email", "role", "skill", "is_active")
    list_filter = ("role",)


class HistoryInline(admin.TabularInline):
    model = StatusHistory
    extra = 0
    readonly_fields = ("old_status", "new_status", "changed_by", "note", "changed_at")
    can_delete = False


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "status", "priority", "customer", "provider", "created_at")
    list_filter = ("status", "category", "priority")
    search_fields = ("title", "address", "customer__username")
    inlines = [HistoryInline]
