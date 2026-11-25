import re
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Category, Item, Review

RATINGS = ["Excellent", "Good", "Fair", "Poor"]
login_req = login_required(login_url="login")


def _cats(text):
    """'Books, gaming' -> ['books', 'gaming'] (single lowercase words only)."""
    return sorted(set(re.findall(r"[a-z]+", (text or "").lower())))


def _price(text):
    try:
        p = Decimal((text or "").strip()).quantize(Decimal("0.01"))
        return p if 0 <= p < 10**8 else None
    except (InvalidOperation, ValueError):
        return None


# ---------------------------------------------------------------- shop / items
@login_req
def shop(request):
    cat = request.GET.get("category", "").strip().lower()
    items = (
        Item.objects.select_related("seller")
        .prefetch_related("categories")
        .order_by("-date_posted", "-id")
    )
    if cat:  # Part 4: search by category
        items = items.filter(categories__name=cat)
    return render(request, "shop.html", {"items": items, "cat": cat})


@login_req
def item_add(request):
    f = request.POST
    if request.method == "POST":
        title = f.get("title", "").strip()
        desc = f.get("description", "").strip()
        price = _price(f.get("price"))
        cats = _cats(f.get("categories"))
        today = timezone.localdate()
        if not title or not desc or price is None or not cats:
            messages.error(request, "Fill in every field (price >= 0, 1+ category).")
        elif Item.objects.filter(seller=request.user, date_posted=today).count() >= 2:
            messages.error(request, "You can only post 2 items per day.")
        else:
            try:
                with transaction.atomic():
                    item = Item.objects.create(
                        title=title, description=desc, price=price,
                        seller=request.user, date_posted=today,
                    )
                    item.categories.set(
                        [Category.objects.get_or_create(name=n)[0] for n in cats]
                    )
                messages.success(request, "Item posted!")
                return redirect("item_detail", pk=item.pk)
            except DatabaseError:
                messages.error(request, "The database rejected that (daily limit?).")
    return render(request, "shop/item_form.html", {"f": f})


@login_req
def item_detail(request, pk):
    item = get_object_or_404(
        Item.objects.select_related("seller").prefetch_related("categories"), pk=pk
    )
    reviews = item.reviews.select_related("reviewer").order_by("-review_date", "-id")
    mine = item.seller_id == request.user.id
    can_review = not mine and not reviews.filter(reviewer=request.user).exists()
    return render(request, "shop/item_detail.html", {
        "item": item, "reviews": reviews, "mine": mine,
        "can_review": can_review, "ratings": RATINGS,
    })


def _own_item(request, pk):
    return get_object_or_404(Item, pk=pk, seller=request.user)  # 404 if not yours


@login_req
@require_POST
def item_price(request, pk):
    item = _own_item(request, pk)
    price = _price(request.POST.get("price"))
    if price is None:
        messages.error(request, "Enter a valid price.")
    else:
        item.price = price
        item.save(update_fields=["price"])
        messages.success(request, "Price updated.")
    return redirect("item_detail", pk=pk)


@login_req
@require_POST
def item_delete(request, pk):
    _own_item(request, pk).delete()
    messages.success(request, "Item deleted.")
    return redirect("shop")


@login_req
@require_POST
def item_categories(request, pk):
    item = _own_item(request, pk)
    names = _cats(request.POST.get("categories"))
    if request.POST.get("action") == "add":
        item.categories.add(*[Category.objects.get_or_create(name=n)[0] for n in names])
    else:
        remaining = item.categories.exclude(name__in=names).count()
        if remaining == 0:
            messages.error(request, "An item must keep at least one category.")
        else:
            item.categories.remove(*item.categories.filter(name__in=names))
    return redirect("item_detail", pk=pk)


# --------------------------------------------------------------------- reviews
@login_req
@require_POST
def review_add(request, pk):
    item = get_object_or_404(Item, pk=pk)
    rating = request.POST.get("rating")
    comment = request.POST.get("comment", "").strip()[:200]
    today = timezone.localdate()
    if item.seller_id == request.user.id:
        messages.error(request, "You can't review your own item.")
    elif rating not in RATINGS or not comment:
        messages.error(request, "Pick a rating and write a comment.")
    elif Review.objects.filter(item=item, reviewer=request.user).exists():
        messages.error(request, "You already reviewed this item.")
    elif Review.objects.filter(reviewer=request.user, review_date=today).count() >= 2:
        messages.error(request, "You can only submit 2 reviews per day.")
    else:
        try:
            with transaction.atomic():
                Review.objects.create(item=item, reviewer=request.user,
                                      rating=rating, comment=comment, review_date=today)
            messages.success(request, "Review submitted.")
        except DatabaseError:
            messages.error(request, "The database rejected that review.")
    return redirect("item_detail", pk=pk)


# ------------------------------------------------------------- Part 6 queries
def _queries():
    U = get_user_model()._meta.db_table  # e.g. base_baseuser
    return {
        "1": ("Most expensive item(s) in each category", [], f"""
            SELECT c.name AS category, i.id, i.title, i.price
            FROM base_item i
            JOIN base_item_categories ic ON ic.item_id = i.id
            JOIN base_category c ON c.id = ic.category_id
            WHERE i.price = (SELECT MAX(i2.price) FROM base_item i2
                             JOIN base_item_categories ic2 ON ic2.item_id = i2.id
                             WHERE ic2.category_id = c.id)
            ORDER BY c.name, i.id"""),
        "2": ("Users who posted a category X item and a category Y item on the same day",
              ["x", "y"], f"""
            SELECT DISTINCT u.username, i1.date_posted
            FROM base_item i1
            JOIN base_item_categories a ON a.item_id = i1.id
            JOIN base_category ca ON ca.id = a.category_id AND ca.name = %s
            JOIN base_item i2 ON i2.seller_id = i1.seller_id
                             AND i2.date_posted = i1.date_posted AND i2.id <> i1.id
            JOIN base_item_categories b ON b.item_id = i2.id
            JOIN base_category cb ON cb.id = b.category_id AND cb.name = %s
            JOIN {U} u ON u.id = i1.seller_id
            ORDER BY u.username"""),
        "3": ("Items by a user where every review is Excellent/Good (and 1+ review)",
              ["username"], f"""
            SELECT i.id, i.title, i.price
            FROM base_item i JOIN {U} u ON u.id = i.seller_id
            WHERE u.username = %s
              AND EXISTS (SELECT 1 FROM base_review r WHERE r.item_id = i.id)
              AND NOT EXISTS (SELECT 1 FROM base_review r WHERE r.item_id = i.id
                              AND r.rating NOT IN ('Excellent', 'Good'))"""),
        "4": ("User(s) who posted the most items on a date (YYYY-MM-DD)", ["date"], f"""
            SELECT u.username, COUNT(*) AS items_posted
            FROM base_item i JOIN {U} u ON u.id = i.seller_id
            WHERE i.date_posted = %s
            GROUP BY u.id, u.username
            HAVING COUNT(*) = (SELECT MAX(n) FROM (SELECT COUNT(*) AS n FROM base_item
                                                   WHERE date_posted = %s
                                                   GROUP BY seller_id) t)"""),
        "5": ("Users whose reviews are ALL Poor", [], f"""
            SELECT u.username, COUNT(*) AS reviews_written
            FROM base_review r JOIN {U} u ON u.id = r.reviewer_id
            GROUP BY u.id, u.username
            HAVING COUNT(*) = SUM(CASE WHEN r.rating = 'Poor' THEN 1 ELSE 0 END)"""),
        "6": ("Users whose items have never received a Poor review", [], f"""
            SELECT u.username
            FROM {U} u
            WHERE EXISTS (SELECT 1 FROM base_item i WHERE i.seller_id = u.id)
              AND NOT EXISTS (SELECT 1 FROM base_item i
                              JOIN base_review r ON r.item_id = i.id
                              WHERE i.seller_id = u.id AND r.rating = 'Poor')"""),
    }


@login_req
def queries(request):
    qs = _queries()
    n = request.GET.get("q")
    result = None
    if n in qs:
        title, fields, sql = qs[n]
        params = [request.GET.get(k, "").strip().lower() if k in ("x", "y")
                  else request.GET.get(k, "").strip() for k in fields]
        if n == "4":
            params = params * 2  # date is used twice in the SQL
        if all(params):
            with connection.cursor() as cur:
                cur.execute(sql, params)
                result = {"title": title, "cols": [c[0] for c in cur.description],
                          "rows": cur.fetchall()}
        else:
            messages.error(request, "Please fill in the input(s) for that query.")
    return render(request, "shop/queries.html", {"result": result, "qs": qs})
