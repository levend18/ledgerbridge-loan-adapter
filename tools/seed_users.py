import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.config.settings")


def seed_users():
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from api.storage.models import Membership

    for index in range(1, 4):
        user, _ = get_user_model().objects.get_or_create(username=f"bank00{index}_user")
        user.set_password("demo1234")
        user.save()
        Membership.objects.update_or_create(user=user, defaults={"tenant_id": f"BANK00{index}"})


if __name__ == "__main__":
    seed_users()
