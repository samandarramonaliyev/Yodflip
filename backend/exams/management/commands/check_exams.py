from django.core.management.base import BaseCommand, CommandError

from exams.seedfiles import check


class Command(BaseCommand):
    help = "Validate the exam pack files: exact counts, no duplicates, all fields filled, real translations."

    def handle(self, *args, **opts):
        counts, errors = check()
        for slug, n in counts.items():
            self.stdout.write(f"{slug}: {n}")
        if errors:
            for e in errors:
                self.stderr.write(f"  x {e}")
            raise CommandError(f"{len(errors)} problem(s) in the exam pack files")
        self.stdout.write(self.style.SUCCESS("Exam packs OK"))
