from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator


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

class Category(models.Model):
    # one lowercase word, e.g. electronics / books / gaming
    name = models.CharField(
        max_length=30,
        unique=True,
        validators=[RegexValidator(r"^[a-z]+$", "Lowercase letters only.")],
    )

    def __str__(self):
        return self.name


class Item(models.Model):
    # id (AUTO_INCREMENT) is created automatically by Django
    title = models.CharField(max_length=100)
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    date_posted = models.DateField(default=timezone.localdate)
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="items"
    )
    categories = models.ManyToManyField(Category, related_name="items")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="item_price_nonneg"),
        ]

    def __str__(self):
        return self.title


class Review(models.Model):
    RATINGS = [(r, r) for r in ("Excellent", "Good", "Fair", "Poor")]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.CharField(max_length=9, choices=RATINGS)
    comment = models.CharField(max_length=200)
    review_date = models.DateField(default=timezone.localdate)

    class Meta:
        constraints = [
            # rule: only one review per user per item
            models.UniqueConstraint(
                fields=["item", "reviewer"], name="one_review_per_item"
            ),
            models.CheckConstraint(
                condition=Q(rating__in=["Excellent", "Good", "Fair", "Poor"]),
                name="rating_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        # rule: reviews can't be modified once submitted (also a DB trigger)
        if not self._state.adding:
            raise ValidationError("Reviews cannot be modified.")
        super().save(*args, **kwargs)
