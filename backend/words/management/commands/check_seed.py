from django.core.management.base import BaseCommand, CommandError

from words.seedcheck import check_seed


class Command(BaseCommand):
    help = "Validate the vocabulary seed files: exact counts per level, no duplicates, no empty fields."

    def handle(self, *args, **opts):
        counts, errors = check_seed()
        for track, levels in counts.items():
            total = sum(levels.values())
            row = "  ".join(f"{lv}={n}" for lv, n in levels.items())
            self.stdout.write(f"{track.upper()}: {row}  total={total}")
        if errors:
            for e in errors:
                self.stderr.write(f"  ✗ {e}")
            raise CommandError(f"{len(errors)} problem(s) in the seed files")
        self.stdout.write(self.style.SUCCESS("Seed OK"))
