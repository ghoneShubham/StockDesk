# Generated manually for Day 14 EmailOutbox

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailOutbox",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("to_addresses", models.JSONField(default=list)),
                ("subject", models.CharField(max_length=255)),
                ("body_text", models.TextField()),
                ("body_html", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=5)),
                ("last_error", models.TextField(blank=True, default="")),
                ("idempotency_key", models.CharField(blank=True, max_length=128, null=True, unique=True)),
                ("next_attempt_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name_plural": "email outbox",
                "ordering": ["created_at"],
                "indexes": [
                    models.Index(fields=["status", "next_attempt_at"], name="core_emailo_status_7a2c1d_idx"),
                ],
            },
        ),
    ]
