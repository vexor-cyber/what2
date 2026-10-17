import mimetypes

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from .models import SitePreferences, StudyBook, Subscription, WorkbookPageScan


User = get_user_model()


def home(request):
    return catalog(request)


def catalog(request):
    books = StudyBook.objects.filter(is_published=True)
    grade = request.GET.get("grade", "")
    subject = request.GET.get("subject", "")
    search = request.GET.get("q", "").strip()
    if grade in {"8", "9"}:
        books = books.filter(grade=grade)
    if subject:
        books = books.filter(subject=subject)
    if search:
        books = books.filter(title__icontains=search) | books.filter(subject__icontains=search)
    subjects = StudyBook.objects.filter(is_published=True)
    if grade in {"8", "9"}:
        subjects = subjects.filter(grade=grade)
    subjects = subjects.values_list("subject", flat=True).distinct().order_by("subject")
    return render(
        request,
        "library/catalog.html",
        {"books": books, "grade": grade, "subject": subject, "search": search, "subjects": subjects},
    )


@login_required
def workbook_detail(request, workbook_id):
    workbook = get_object_or_404(StudyBook, pk=workbook_id, is_published=True)
    return render(
        request,
        "library/workbook_detail.html",
        {"workbook": workbook, "page_scans": workbook.page_scans.all()},
    )


def workbook_cover(request, workbook_id):
    workbook = get_object_or_404(StudyBook, pk=workbook_id, is_published=True)
    if not workbook.cover_image:
        raise Http404("Обкладинку не завантажено.")
    try:
        image = workbook.cover_image.open("rb")
    except (FileNotFoundError, OSError) as error:
        raise Http404("Файл обкладинки не знайдено.") from error
    content_type, _ = mimetypes.guess_type(workbook.cover_image.name)
    response = FileResponse(image, content_type=content_type or "application/octet-stream")
    response["Cache-Control"] = "public, max-age=3600"
    return response


@login_required
def page_scan_file(request, workbook_id, scan_id):
    if not request.user.is_staff:
        try:
            has_access = request.user.subscription.is_active
        except Subscription.DoesNotExist:
            has_access = False
        if not has_access:
            return redirect("subscription")
    scan = get_object_or_404(WorkbookPageScan, pk=scan_id, workbook_id=workbook_id)
    try:
        image = scan.image.open("rb")
    except (FileNotFoundError, OSError) as error:
        raise Http404("Зображення сторінки не знайдено.") from error
    content_type, _ = mimetypes.guess_type(scan.image.name)
    response = FileResponse(image, content_type=content_type or "application/octet-stream")
    response["Cache-Control"] = "private, no-store"
    return response


def settings_page(request):
    subscription = getattr(request.user, "subscription", None) if request.user.is_authenticated else None
    return render(request, "library/settings.html", {"subscription": subscription})


def subscription_page(request):
    subscription = getattr(request.user, "subscription", None) if request.user.is_authenticated else None
    return render(request, "library/subscription.html", {"subscription": subscription})


def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Обліковий запис створено.")
        return redirect("subscription")
    return render(request, "registration/register.html", {"form": form})