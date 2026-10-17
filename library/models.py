import calendar
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def validate_image_size(image):
    if image.size > 10 * 1024 * 1024:
        raise ValidationError("Зображення має бути не більшим за 10 МБ.")


def validate_page_scan_size(image):
    validate_image_size(image)


class StudyBook(models.Model):
    class Grade(models.IntegerChoices):
        EIGHT = 8, "8 клас"
        NINE = 9, "9 клас"

    grade = models.PositiveSmallIntegerField("клас", choices=Grade.choices)
    subject = models.CharField("предмет", max_length=80)
    title = models.CharField("назва зошита", max_length=160)
    publisher = models.CharField("видавництво", max_length=120, blank=True)
    edition = models.CharField("рік або видання", max_length=60, blank=True)
    description = models.TextField("опис", blank=True)
    cover_image = models.ImageField(
        "фото обкладинки", upload_to="workbooks/covers/", blank=True, validators=[validate_image_size]
    )
    cover_url = models.URLField("посилання на обкладинку", blank=True)
    is_published = models.BooleanField("опублікований", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["grade", "subject", "title"]
        verbose_name = "зошит"
        verbose_name_plural = "зошити"

    def __str__(self):
        return f"{self.grade} клас · {self.title}"


class ExerciseGuide(models.Model):
    workbook = models.ForeignKey(StudyBook, on_delete=models.CASCADE, related_name="guides")
    page_number = models.PositiveSmallIntegerField(
        "сторінка", validators=[MinValueValidator(1), MaxValueValidator(50)]
    )
    exercise_number = models.CharField("номер вправи", max_length=40)
    topic = models.CharField("тема", max_length=160, blank=True)
    hint = models.TextField("підказка", blank=True)
    explanation = models.TextField("пояснення крок за кроком")
    answer_check = models.CharField("коротка відповідь для перевірки", max_length=300, blank=True)

    class Meta:
        ordering = ["page_number", "exercise_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["workbook", "page_number", "exercise_number"],
                name="unique_workbook_page_exercise",
            )
        ]
        verbose_name = "пояснення до вправи"
        verbose_name_plural = "пояснення до вправ"

    def __str__(self):
        return f"Сторінка {self.page_number} · №{self.exercise_number}"


def page_scan_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"workbooks/{instance.workbook_id}/page-{instance.page_number}{extension}"


class WorkbookPageScan(models.Model):
    workbook = models.ForeignKey(StudyBook, on_delete=models.CASCADE, related_name="page_scans")
    page_number = models.PositiveSmallIntegerField(
        "сторінка", validators=[MinValueValidator(1), MaxValueValidator(50)]
    )
    image = models.ImageField(
        "фото сторінки",
        upload_to=page_scan_upload_path,
        validators=[validate_image_size],
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["page_number"]
        constraints = [models.UniqueConstraint(fields=["workbook", "page_number"], name="unique_workbook_scan_page")]
        verbose_name = "фото сторінки"
        verbose_name_plural = "фото сторінок"

    def __str__(self):
        return f"{self.workbook} · сторінка {self.page_number}"


class Subscription(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription")
    active_until = models.DateTimeField("доступ до", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "підписка"
        verbose_name_plural = "підписки"

    @property
    def is_active(self):
        return self.active_until is not None and self.active_until > timezone.now()

    def grant_month(self):
        start = self.active_until if self.is_active else timezone.now()
        month = start.month % 12 + 1
        year = start.year + (start.month == 12)
        day = min(start.day, calendar.monthrange(year, month)[1])
        self.active_until = start.replace(year=year, month=month, day=day)
        self.save(update_fields=["active_until", "updated_at"])
        return self.active_until


class SitePreferences(models.Model):
    class AdminTheme(models.TextChoices):
        LIGHT = "light", "Світла, високий контраст"
        DARK = "dark", "Темна"

    site_name = models.CharField("назва сайту", max_length=80, default="Крок")
    announcement = models.CharField("оголошення", max_length=180, blank=True)
    admin_theme = models.CharField(
        "кольорова тема адмінпанелі",
        max_length=8,
        choices=AdminTheme.choices,
        default=AdminTheme.LIGHT,
    )

    class Meta:
        verbose_name = "налаштування сайту"
        verbose_name_plural = "налаштування сайту"

    def __str__(self):
        return self.site_name

    @classmethod
    def current(cls):
        preferences, _ = cls.objects.get_or_create(pk=1)
        return preferences