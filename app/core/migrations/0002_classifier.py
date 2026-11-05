from django.db import migrations


def seed(apps, schema_editor):
    Group = apps.get_model("core", "CategoryGroup")
    Item = apps.get_model("core", "CategoryItem")
    for name, elements in [
        ("Оборудование", ["Проектор", "Принтер", "Компьютерный класс"]),
        ("Помещение", ["Кабинет", "Коридор", "Столовая"]),
        ("Обслуживание", ["Wi-Fi", "Электрика", "Мебель"]),
    ]:
        group, _ = Group.objects.get_or_create(name=name)
        for element in elements:
            Item.objects.get_or_create(group=group, name=element)


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
