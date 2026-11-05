from django.conf import settings


def get_icon(name):
    icon = getattr(settings, "BOT_CONFIG", {}).get("emojis", {}).get(name, {})
    return str(icon.get("id", "")), str(icon.get("fallback", "•"))
