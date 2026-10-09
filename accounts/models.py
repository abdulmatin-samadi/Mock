from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from core.storage import avatar_path
from core.validators import validate_image


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        extra.setdefault("role", User.Role.STUDENT)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role=User.Role.ADMIN)
        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        ADMIN = "admin", "Admin"

    username = None
    email = models.EmailField("email address", unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    profile_photo = models.ImageField(upload_to=avatar_path, blank=True, validators=[validate_image])
    phone_number = models.CharField(max_length=32, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.STUDENT, db_index=True)
    # Visitors who start their free mock without an account get a temporary guest student.
    is_guest = models.BooleanField(default=False, db_index=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        ordering = ["-date_joined"]
        indexes = [models.Index(fields=["role", "is_active"])]

    def __str__(self):
        return f"{self.get_full_name()} <{self.email}>"

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        if self.is_superuser:
            self.role = self.Role.ADMIN
        # Only admins may use the built-in Django admin.
        self.is_staff = self.role == self.Role.ADMIN
        super().save(*args, **kwargs)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def full_name(self):
        return self.get_full_name()

    @property
    def initials(self):
        return ((self.first_name[:1] + self.last_name[:1]) or self.email[:1]).upper()

    @property
    def is_admin(self):
        return self.is_active and (self.role == self.Role.ADMIN or self.is_superuser)

    @property
    def is_student(self):
        return self.is_active and self.role == self.Role.STUDENT
