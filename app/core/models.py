import uuid
from django.conf import settings
from django.db import models


class CategoryGroup(models.Model):
    name = models.CharField("Название", max_length=100, unique=True)
    active = models.BooleanField("Доступна", default=True)

    class Meta:
        verbose_name = "группа"
        verbose_name_plural = "Группы"
        ordering = ["id"]

    def __str__(self):
        return self.name


class CategoryItem(models.Model):
    group = models.ForeignKey(CategoryGroup, on_delete=models.PROTECT, verbose_name="Группа")
    name = models.CharField("Название", max_length=100)
    active = models.BooleanField("Доступен", default=True)

    class Meta:
        verbose_name = "элемент"
        verbose_name_plural = "Элементы"
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["group", "name"], name="unique_group_item")]

    def __str__(self):
        return f"{self.group} / {self.name}"


class Ticket(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новая"
        WORK = "work", "В работе"
        DONE = "done", "Выполнена"
        REJECTED = "rejected", "Отклонена"

    key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    platform = models.CharField(max_length=16, default="telegram", db_index=True)
    telegram_id = models.BigIntegerField()
    nickname = models.CharField(max_length=64, blank=True, default="")
    max_chat_id = models.BigIntegerField(null=True, blank=True)
    applicant = models.CharField(max_length=200)
    contact = models.CharField(max_length=300)
    item = models.ForeignKey(CategoryItem, on_delete=models.PROTECT)
    category_label = models.CharField(max_length=205)
    description = models.TextField()
    status = models.CharField(max_length=10, choices=Status, default=Status.NEW, db_index=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-id"]

    @property
    def number(self):
        return f"З-{self.pk:06d}"

    @property
    def phone_display(self):
        from app.core.phones import display_phone
        return display_phone(self.contact)

    @property
    def messenger_label(self):
        return "MAX" if self.platform == "max" else "Telegram"

    @property
    def chat_url(self):
        nick = self.nickname.strip().lstrip("@")
        if self.platform == "max":
            return f"https://web.max.ru/{self.max_chat_id}" if self.max_chat_id else ""
        return f"https://t.me/{nick}" if nick else f"tg://user?id={self.telegram_id}"


class History(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    actor_label = models.CharField(max_length=200)
    action = models.CharField(max_length=30)
    comment = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Ticket.Status)
    assignee_label = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class Notification(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    next_attempt = models.DateTimeField(db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    lease_key = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["id"]


class BotDialog(models.Model):
    platform = models.CharField(max_length=16, default="telegram")
    telegram_id = models.BigIntegerField()
    step = models.CharField(max_length=20, default="idle")
    data = models.JSONField(default=dict)
    screen_message_id = models.BigIntegerField(null=True, blank=True)
    screen_mid = models.CharField(max_length=128, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["platform", "telegram_id"], name="unique_dialog_channel")]


class BotCursor(models.Model):
    name = models.CharField(max_length=50, unique=True)
    offset = models.BigIntegerField(default=0)


class StaffSecret(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="secret")
    sealed = models.TextField()


class EmailCode(models.Model):
    email = models.EmailField(db_index=True)
    digest = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class LoginGuard(models.Model):
    username = models.CharField(max_length=150, unique=True)
    failures = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
