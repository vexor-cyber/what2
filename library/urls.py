from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("workbooks/", views.catalog, name="catalog"),
    path("workbooks/<int:workbook_id>/cover/", views.workbook_cover, name="workbook_cover"),
    path("workbooks/<int:workbook_id>/", views.workbook_detail, name="workbook_detail"),
    path("workbooks/<int:workbook_id>/pages/<int:scan_id>/", views.page_scan_file, name="page_scan_file"),
    path("settings/", views.settings_page, name="settings"),
    path("subscription/", views.subscription_page, name="subscription"),
    path("register/", views.register, name="register"),
]