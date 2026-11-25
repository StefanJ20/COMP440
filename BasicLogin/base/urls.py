from django.urls import path
from . import views, shop_views  # type: ignore

urlpatterns = [
    path("", views.index, name="index"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),

    # --- shop (MS Paint themed) ---
    path("shop/", shop_views.shop, name="shop"),
    path("shop/sell/", shop_views.item_add, name="item_add"),
    path("shop/queries/", shop_views.queries, name="queries"),
    path("shop/item/<int:pk>/", shop_views.item_detail, name="item_detail"),
    path("shop/item/<int:pk>/price/", shop_views.item_price, name="item_price"),
    path("shop/item/<int:pk>/delete/", shop_views.item_delete, name="item_delete"),
    path("shop/item/<int:pk>/categories/", shop_views.item_categories, name="item_categories"),
    path("shop/item/<int:pk>/review/", shop_views.review_add, name="review_add"),
]
