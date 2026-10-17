from .models import SitePreferences


def site_preferences(request):
    return {"site_preferences": SitePreferences.current()}