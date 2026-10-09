"""Keep Django auth Groups in sync with the user's role.

Groups carry real Django model permissions (visible in /django-admin/), while
the application enforces access with role checks + object-level permissions.
"""
from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import User

ROLE_GROUPS = {
    User.Role.STUDENT: "Students",
    User.Role.ADMIN: "Admins",
}

STUDENT_PERMS = {
    "results": ["view_examattempt", "view_result", "view_answer", "view_fullmockattempt"],
    "writing": ["add_writingsubmission", "view_writingsubmission", "view_writingevaluation"],
    "speaking": ["add_speakingsubmission", "view_speakingsubmission", "view_speakingevaluation"],
}


@receiver(post_migrate)
def create_role_groups(sender, **kwargs):
    # Run once, after the last local app so all model permissions exist.
    if sender.name != "admin_dashboard":
        return
    students, _ = Group.objects.get_or_create(name="Students")
    admins, _ = Group.objects.get_or_create(name="Admins")
    s_perms = []
    for app_label, codenames in STUDENT_PERMS.items():
        s_perms += list(Permission.objects.filter(content_type__app_label=app_label, codename__in=codenames))
    students.permissions.set(s_perms)
    admins.permissions.set(Permission.objects.all())


@receiver(post_save, sender=User)
def sync_user_group(sender, instance, **kwargs):
    group_name = ROLE_GROUPS.get(instance.role)
    if not group_name:
        return
    groups = Group.objects.filter(name__in=ROLE_GROUPS.values())
    current = set(instance.groups.filter(pk__in=groups).values_list("name", flat=True))
    if current != {group_name}:
        instance.groups.remove(*groups)
        group, _ = Group.objects.get_or_create(name=group_name)
        instance.groups.add(group)
