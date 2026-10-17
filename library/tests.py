from datetime import datetime, timezone as datetime_timezone
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .models import ExerciseGuide, SitePreferences, StudyBook, Subscription, WorkbookPageScan


User = get_user_model()


def make_png():
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


class LibraryTests(TestCase):
    def setUp(self):
        self.book = StudyBook.objects.create(
            grade=8,
            subject="Алгебра",
            title="Алгебра · робочий зошит",
            is_published=True,
        )
        self.guide = ExerciseGuide.objects.create(
            workbook=self.book,
            page_number=12,
            exercise_number="4",
            explanation="Спочатку перенеси відомі доданки в один бік рівняння.",
        )
        self.user = User.objects.create_user(username="student", password="test-passphrase-123")

    def activate_subscription(self):
        subscription = self.user.subscription
        subscription.active_until = timezone.now() + timezone.timedelta(days=1)
        subscription.save(update_fields=["active_until"])
        return subscription

    def test_catalog_is_public_and_filters_by_grade(self):
        StudyBook.objects.create(grade=9, subject="Геометрія", title="Геометрія", is_published=True)
        response = self.client.get("/workbooks/?grade=8")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.book.title)
        self.assertNotContains(response, "Геометрія")

    def test_new_account_receives_inactive_subscription(self):
        self.assertTrue(Subscription.objects.filter(user=self.user).exists())
        self.assertFalse(self.user.subscription.is_active)

    def test_registration_creates_account_and_redirects_to_subscription(self):
        response = self.client.post(
            "/register/",
            {
                "username": "new-student",
                "password1": "A-long-and-unique-test-password-928",
                "password2": "A-long-and-unique-test-password-928",
            },
        )
        new_user = User.objects.get(username="new-student")
        self.assertRedirects(response, "/subscription/", fetch_redirect_response=False)
        self.assertTrue(new_user.subscription)
        self.assertFalse(new_user.subscription.is_active)

    def test_unpaid_account_is_redirected_from_explanations(self):
        self.client.force_login(self.user)
        response = self.client.get(f"/workbooks/{self.book.pk}/")
        self.assertRedirects(response, "/subscription/", fetch_redirect_response=False)

    def test_active_account_can_read_explanation(self):
        self.activate_subscription()
        self.client.force_login(self.user)
        response = self.client.get(f"/workbooks/{self.book.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.guide.explanation)

    def test_expired_subscription_does_not_unlock_explanations(self):
        subscription = self.user.subscription
        subscription.active_until = timezone.now() - timezone.timedelta(seconds=1)
        subscription.save(update_fields=["active_until"])
        self.client.force_login(self.user)
        response = self.client.get(f"/workbooks/{self.book.pk}/")
        self.assertRedirects(response, "/subscription/", fetch_redirect_response=False)

    def test_subscription_grant_extends_access_by_calendar_month(self):
        subscription = self.activate_subscription()
        original_expiry = subscription.active_until
        new_expiry = subscription.grant_month()
        self.assertGreater(new_expiry, original_expiry)
        self.assertTrue(subscription.is_active)

    def test_subscription_grant_handles_end_of_month(self):
        subscription = self.user.subscription
        fixed_now = datetime(2025, 1, 31, 12, tzinfo=datetime_timezone.utc)
        with patch("library.models.timezone.now", return_value=fixed_now):
            expiry = subscription.grant_month()
        self.assertEqual(expiry, datetime(2025, 2, 28, 12, tzinfo=datetime_timezone.utc))

    def test_site_owner_can_grant_subscription_to_self_and_another_user(self):
        owner = User.objects.create_superuser(username="owner", password="owner-test-password-927")
        self.client.force_login(owner)

        changelist_url = reverse("admin:library_subscription_changelist")
        changelist_response = self.client.get(changelist_url)
        self.assertContains(changelist_response, "Відкрити мені доступ на місяць")

        self_response = self.client.post(reverse("admin:library_subscription_grant_self"))
        owner.subscription.refresh_from_db()
        self.assertEqual(self_response.status_code, 302)
        self.assertTrue(owner.subscription.is_active)

        action_response = self.client.post(
            changelist_url,
            {
                "action": "grant_one_month",
                "index": "0",
                "_selected_action": [str(self.user.subscription.pk)],
            },
        )
        self.user.subscription.refresh_from_db()
        self.assertEqual(action_response.status_code, 302)
        self.assertTrue(self.user.subscription.is_active)

    def test_regular_staff_cannot_grant_subscription(self):
        staff = User.objects.create_user(
            username="staff",
            password="staff-test-password-927",
            is_staff=True,
        )
        self.client.force_login(staff)
        response = self.client.post(reverse("admin:library_subscription_grant_self"))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(staff.subscription.is_active)
        self.assertFalse(self.user.subscription.is_active)

    def test_owner_can_change_admin_theme_and_it_is_applied(self):
        owner = User.objects.create_superuser(username="theme-owner", password="owner-theme-password-927")
        preferences = SitePreferences.current()
        self.client.force_login(owner)
        change_url = reverse("admin:library_sitepreferences_change", args=[preferences.pk])
        response = self.client.post(
            change_url,
            {"site_name": preferences.site_name, "announcement": "", "admin_theme": "dark", "_save": ""},
        )
        preferences.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(preferences.admin_theme, SitePreferences.AdminTheme.DARK)
        admin_response = self.client.get(reverse("admin:index"))
        self.assertContains(admin_response, "--body-bg: #151a17;")

    def test_page_limit_matches_initial_material_range(self):
        invalid_guide = ExerciseGuide(
            workbook=self.book,
            page_number=51,
            exercise_number="1",
            explanation="Пояснення",
        )
        with self.assertRaises(ValidationError):
            invalid_guide.full_clean()

    def test_settings_are_public_even_without_subscription(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/settings/").status_code, 200)
        self.assertEqual(self.client.get("/subscription/").status_code, 200)

    def test_page_image_is_only_served_with_active_subscription(self):
        image_data = make_png()
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            scan = WorkbookPageScan.objects.create(
                workbook=self.book,
                page_number=1,
                image=SimpleUploadedFile("page.png", image_data, content_type="image/png"),
            )
            self.client.force_login(self.user)
            url = f"/workbooks/{self.book.pk}/pages/{scan.pk}/"
            self.assertRedirects(self.client.get(url), "/subscription/", fetch_redirect_response=False)

            self.activate_subscription()
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertEqual(b"".join(response.streaming_content), image_data)

    def test_workbook_cover_is_public_but_not_the_page_scans(self):
        image_data = make_png()
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self.book.cover_image = SimpleUploadedFile("cover.png", image_data, content_type="image/png")
            self.book.save(update_fields=["cover_image"])
            response = self.client.get(f"/workbooks/{self.book.pk}/cover/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), image_data)

    def test_seed_command_adds_two_original_physics_books_once(self):
        call_command("seed_physics")
        call_command("seed_physics")
        seeded_books = StudyBook.objects.filter(subject="Фізика")
        self.assertEqual(seeded_books.count(), 2)
        self.assertEqual(
            sum(book.guides.count() for book in seeded_books),
            8,
        )