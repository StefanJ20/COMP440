from django.contrib import admin

from base.models import Category, Item, Review, BaseUser

# Register your models here.

admin.site.register(BaseUser)
admin.site.register(Category)
admin.site.register(Item)
admin.site.register(Review)