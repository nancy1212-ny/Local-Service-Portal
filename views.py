from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AssignForm, ServiceRequestForm, SignUpForm, StatusUpdateForm
from .models import ServiceRequest, StatusHistory, User

S = ServiceRequest.Status


def signup(request):
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome! Your account has been created.")
        return redirect("dashboard")
    return render(request, "registration/signup.html", {"form": form})


def visible_requests(user):
    """Role-based queryset: each role only sees what it should."""
    qs = ServiceRequest.objects.select_related("customer", "provider")
    if user.is_dispatcher:
        return qs
    if user.is_provider:
        return qs.filter(provider=user)
    return qs.filter(customer=user)


@login_required
def dashboard(request):
    user = request.user
    qs = visible_requests(user)

    status_filter = request.GET.get("status", "")
    search = request.GET.get("q", "").strip()
    listing = qs
    if status_filter in S.values:
        listing = listing.filter(status=status_filter)
    if search:
        listing = listing.filter(
            Q(title__icontains=search) | Q(category__icontains=search) | Q(address__icontains=search)
        )

    counts = {row["status"]: row["n"] for row in qs.values("status").annotate(n=Count("id"))}
    stats = [(label, value, counts.get(value, 0)) for value, label in S.choices]

    return render(request, "tracker/dashboard.html", {
        "requests": listing, "stats": stats, "status_filter": status_filter, "search": search,
    })


@login_required
def create_request(request):
    if not request.user.is_customer:
        raise PermissionDenied("Only customers can raise service requests.")
    form = ServiceRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.customer = request.user
        obj.save()
        StatusHistory.objects.create(
            request=obj, old_status=S.PENDING, new_status=S.PENDING,
            changed_by=request.user, note="Request created",
        )
        messages.success(request, f"Request #{obj.pk} submitted.")
        return redirect("request_detail", pk=obj.pk)
    return render(request, "tracker/request_form.html", {"form": form})


@login_required
def request_detail(request, pk):
    obj = get_object_or_404(visible_requests(request.user), pk=pk)
    user = request.user
    ctx = {"obj": obj, "history": obj.history.select_related("changed_by")}

    if user.is_dispatcher and obj.status in (S.PENDING, S.ASSIGNED):
        ctx["assign_form"] = AssignForm(request_obj=obj)

    allowed = obj.allowed_next_statuses()
    allowed = [s for s in allowed if _user_may_set(user, obj, s)]
    # Assignment goes through the assign form, not the generic status form.
    allowed = [s for s in allowed if s != S.ASSIGNED]
    if allowed:
        ctx["status_form"] = StatusUpdateForm(request_obj=obj, allowed=allowed)

    # Progress tracker (cancelled requests show separately).
    steps = [S.PENDING, S.ASSIGNED, S.IN_PROGRESS, S.COMPLETED]
    if obj.status != S.CANCELLED:
        idx = steps.index(obj.status)
        ctx["steps"] = [
            {"label": S(s).label, "done": i < idx, "current": i == idx}
            for i, s in enumerate(steps)
        ]
    return render(request, "tracker/request_detail.html", ctx)


def _user_may_set(user, obj, new_status):
    """Who is allowed to perform which transition."""
    if user.is_dispatcher:
        return new_status in (S.PENDING, S.CANCELLED, S.ASSIGNED)
    if user.is_provider and obj.provider_id == user.id:
        return new_status in (S.IN_PROGRESS, S.COMPLETED, S.PENDING)  # PENDING = decline job
    if user.is_customer and obj.customer_id == user.id:
        return new_status == S.CANCELLED
    return False


@login_required
def assign_request(request, pk):
    if not request.user.is_dispatcher:
        raise PermissionDenied("Only admins can assign requests.")
    obj = get_object_or_404(ServiceRequest, pk=pk)
    if request.method != "POST":
        return redirect("request_detail", pk=pk)
    form = AssignForm(request.POST, request_obj=obj)
    if form.is_valid():
        try:
            obj.assign_to(form.cleaned_data["provider"], request.user, form.cleaned_data["note"])
            messages.success(request, f"Request #{obj.pk} assigned to {obj.provider.username}.")
        except ValidationError as e:
            messages.error(request, "; ".join(e.messages))
    else:
        messages.error(request, "Please choose a valid provider.")
    return redirect("request_detail", pk=pk)


@login_required
def update_status(request, pk):
    obj = get_object_or_404(visible_requests(request.user), pk=pk)
    if request.method != "POST":
        return redirect("request_detail", pk=pk)
    allowed = [s for s in obj.allowed_next_statuses()
               if s != S.ASSIGNED and _user_may_set(request.user, obj, s)]
    form = StatusUpdateForm(request.POST, request_obj=obj, allowed=allowed)
    if not allowed:
        raise PermissionDenied("You cannot change this request's status.")
    if form.is_valid():
        try:
            obj.change_status(form.cleaned_data["status"], request.user, form.cleaned_data["note"])
            messages.success(request, f"Status updated to {obj.get_status_display()}.")
        except ValidationError as e:
            messages.error(request, "; ".join(e.messages))
    else:
        messages.error(request, "Invalid status change.")
    return redirect("request_detail", pk=pk)
