from django.contrib.auth.models import AbstractUser
from django.db import models


class BaseUser(AbstractUser):
    phone_number = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return self.username