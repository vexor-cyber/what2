from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.urls import path
from django.utils import timezone

from .models import ExerciseGuide, SitePreferences, StudyBook, Subscription, WorkbookPageScan


class ExerciseGuideInline(admin.TabularInline):
    model = ExerciseGuide
    extra = 0


class WorkbookPageScanInline(admin.TabularInline):
    model = WorkbookPageScan
    extra = 0


@admin.register(StudyBook)
class StudyBookAdmin(admin.ModelAdmin):
    list_display = ("title", "grade", "subject", "publisher", "is_published")
    list_filter = ("grade", "subject", "is_published")
    search_fields = ("title", "subject", "publisher")
    inlines = (WorkbookPageScanInline, ExerciseGuideInline)


@admin.register(WorkbookPageScan)
class WorkbookPageScanAdmin(admin.ModelAdmin):
    list_display = ("workbook", "page_number", "uploaded_at")
    list_filter = ("workbook__grade", "workbook__subject")
    search_fields = ("workbook__title",)


@admin.register(ExerciseGuide)
class ExerciseGuideAdmin(admin.ModelAdmin):
    list_display = ("workbook", "page_number", "exercise_number", "topic")
    list_filter = ("workbook__grade", "workbook__subject")
    search_fields = ("workbook__title", "exercise_number", "topic")


@admin.action(description="Открыть доступ ещё на месяц")
def grant_one_month(modeladmin, request, queryset):
    for subscription in queryset:
        subscription.grant_month()
    modeladmin.message_user(request, "Місячний доступ відкрито для вибраних акаунтів.", messages.SUCCESS)


@admin.action(description="Отключить доступ")
def revoke_access(modeladmin, request, queryset):
    queryset.update(active_until=None)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "active_until", "updated_at")
    list_filter = ("active_until",)
    search_fields = ("user__username", "user__email")
    actions = (grant_one_month, revoke_access)
    change_list_template = "admin/library/subscription/change_list.html"

    def get_urls(self):
        custom_urls = [
            path(
                "grant-self/",
                self.admin_site.admin_view(self.grant_self_access),
                name="library_subscription_grant_self",
            )
        ]
        return custom_urls + super().get_urls()

    def grant_self_access(self, request):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not request.user.is_superuser:
            return HttpResponseForbidden()
        subscription, _ = Subscription.objects.get_or_create(user=request.user)
        expiry = subscription.grant_month()
        local_expiry = timezone.localtime(expiry).strftime("%d.%m.%Y %H:%M")
        self.message_user(request, f"Твій доступ активний до {local_expiry}.", messages.SUCCESS)
        return redirect("admin:library_subscription_changelist")

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(SitePreferences)
class SitePreferencesAdmin(admin.ModelAdmin):
    list_display = ("site_name", "admin_theme", "announcement")
    fields = ("site_name", "announcement", "admin_theme")


class RestrictedUserAdmin(UserAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


admin.site.unregister(User)
admin.site.register(User, RestrictedUserAdmin)
admin.site.site_header = "Крок · керування"
admin.site.site_title = "Крок"
admin.site.index_title = "Навчальна бібліотека"