from django.core.management.base import BaseCommand

from telegram_bot import services
from telegram_bot.setup import configure_telegram, webhook_url


class Command(BaseCommand):
    help = "Set the Telegram webhook, commands and Mini App menu button. Also prints the reminder cron URL."

    def handle(self, *args, **opts):
        ok = configure_telegram()
        self.stdout.write(
            ("Webhook set: " if ok else "Webhook NOT set (see log): ") + (webhook_url() and "/bot/webhook/<secret>/")
        )
        cron = services.webapp_url(f"/bot/cron/{services.cron_secret()}/")
        self.stdout.write(f"Reminder cron URL (keep it secret, call every 10 min): {cron or '/bot/cron/<secret>/'}")
