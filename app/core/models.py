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
    telegram_id = models.BigIntegerField()
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
    telegram_id = models.BigIntegerField(unique=True)
    step = models.CharField(max_length=20, default="idle")
    data = models.JSONField(default=dict)
    screen_message_id = models.BigIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class BotCursor(models.Model):
    name = models.CharField(max_length=50, unique=True)
    offset = models.BigIntegerField(default=0)
