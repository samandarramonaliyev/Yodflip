from django.db import migrations

TIERS = [
    # code, order, emoji, uz, ru, en, color, promote, demote
    ("bronze", 0, "🥉", "Bronza", "Бронза", "Bronze", "#CD7F32", 7, 5),
    ("silver", 1, "🥈", "Kumush", "Серебро", "Silver", "#A0A4AB", 7, 5),
    ("gold", 2, "🥇", "Oltin", "Золото", "Gold", "#F5B700", 3, 5),
]


def seed(apps, schema_editor):
    Tier = apps.get_model("leagues", "LeagueTier")
    for code, order, emoji, uz, ru, en, color, promote, demote in TIERS:
        Tier.objects.update_or_create(
            code=code,
            defaults=dict(
                order=order, emoji=emoji, name_uz=uz, name_ru=ru, name_en=en, color=color, promote=promote, demote=demote
            ),
        )


class Migration(migrations.Migration):
    dependencies = [("leagues", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
