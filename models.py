from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction


class User(AbstractUser):
    """Custom user with a role: customer, provider (worker) or admin (dispatcher)."""

    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        PROVIDER = "provider", "Service Provider"
        ADMIN = "admin", "Admin / Dispatcher"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER)
    phone = models.CharField(max_length=15, blank=True)
    skill = models.CharField(
        max_length=50, blank=True,
        help_text="Provider's service category (e.g. Plumbing). Used to suggest providers.",
    )

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_provider(self):
        return self.role == self.Role.PROVIDER

    @property
    def is_dispatcher(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"


class ServiceRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Category(models.TextChoices):
        PLUMBING = "Plumbing", "Plumbing"
        ELECTRICAL = "Electrical", "Electrical"
        CARPENTRY = "Carpentry", "Carpentry"
        CLEANING = "Cleaning", "Cleaning"
        APPLIANCE = "Appliance Repair", "Appliance Repair"
        PAINTING = "Painting", "Painting"
        OTHER = "Other", "Other"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    # Allowed status transitions (the workflow state machine).
    TRANSITIONS = {
        Status.PENDING: [Status.ASSIGNED, Status.CANCELLED],
        Status.ASSIGNED: [Status.IN_PROGRESS, Status.PENDING, Status.CANCELLED],
        Status.IN_PROGRESS: [Status.COMPLETED],
        Status.COMPLETED: [],
        Status.CANCELLED: [],
    }

    title = models.CharField(max_length=120)
    description = models.TextField()
    category = models.CharField(max_length=30, choices=Category.choices)
    address = models.CharField(max_length=255)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="requests_made"
    )
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="requests_assigned",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.pk} {self.title} [{self.get_status_display()}]"

    # ---- workflow helpers -------------------------------------------------
    def allowed_next_statuses(self):
        return self.TRANSITIONS[self.Status(self.status)]

    def can_transition_to(self, new_status):
        return new_status in self.allowed_next_statuses()

    @transaction.atomic
    def change_status(self, new_status, user, note=""):
        """Validate and apply a status change, recording it in StatusHistory."""
        from django.utils import timezone

        if not self.can_transition_to(new_status):
            raise ValidationError(
                f"Cannot change status from '{self.get_status_display()}' to "
                f"'{self.Status(new_status).label}'."
            )
        old = self.status
        self.status = new_status
        if new_status == self.Status.COMPLETED:
            self.completed_at = timezone.now()
        if new_status == self.Status.PENDING:
            # Provider declined / admin unassigned: free the request for reassignment.
            self.provider = None
            self.assigned_at = None
        self.save()
        StatusHistory.objects.create(
            request=self, old_status=old, new_status=new_status, changed_by=user, note=note
        )

    @transaction.atomic
    def assign_to(self, provider, user, note=""):
        """Assign (or reassign) a provider. Only a pending request can be assigned."""
        from django.utils import timezone

        if provider.role != User.Role.PROVIDER:
            raise ValidationError("Selected user is not a service provider.")
        if self.status not in (self.Status.PENDING, self.Status.ASSIGNED):
            raise ValidationError("Only pending or assigned requests can be (re)assigned.")

        if self.status == self.Status.PENDING:
            self.provider = provider
            self.assigned_at = timezone.now()
            self.save()
            self.change_status(self.Status.ASSIGNED, user, note or f"Assigned to {provider.username}")
        else:  # reassignment while still 'assigned'
            old_provider = self.provider
            self.provider = provider
            self.assigned_at = timezone.now()
            self.save()
            StatusHistory.objects.create(
                request=self,
                old_status=self.status,
                new_status=self.status,
                changed_by=user,
                note=note or f"Reassigned from {old_provider} to {provider.username}",
            )


class StatusHistory(models.Model):
    """Audit trail: one row per status change or reassignment."""

    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name="history")
    old_status = models.CharField(max_length=15, choices=ServiceRequest.Status.choices)
    new_status = models.CharField(max_length=15, choices=ServiceRequest.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    note = models.CharField(max_length=255, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at", "id"]
        verbose_name_plural = "Status history"

    def __str__(self):
        return f"{self.request_id}: {self.old_status} -> {self.new_status}"
