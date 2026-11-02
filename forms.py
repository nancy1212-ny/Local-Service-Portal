from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import ServiceRequest, User


class SignUpForm(UserCreationForm):
    # Admin accounts are created by a superuser, so only two roles are public.
    role = forms.ChoiceField(
        choices=[(User.Role.CUSTOMER, "Customer"), (User.Role.PROVIDER, "Service Provider")]
    )
    skill = forms.ChoiceField(
        choices=[("", "---------")] + list(ServiceRequest.Category.choices),
        required=False,
        label="Service category (providers only)",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone", "role", "skill")

    def clean(self):
        data = super().clean()
        if data.get("role") == User.Role.PROVIDER and not data.get("skill"):
            self.add_error("skill", "Providers must choose a service category.")
        return data


class ServiceRequestForm(forms.ModelForm):
    class Meta:
        model = ServiceRequest
        fields = ["title", "category", "priority", "address", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class AssignForm(forms.Form):
    provider = forms.ModelChoiceField(queryset=User.objects.none())
    note = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, request_obj=None, **kwargs):
        super().__init__(*args, **kwargs)
        providers = User.objects.filter(role=User.Role.PROVIDER, is_active=True)
        if request_obj is not None:
            # Show providers matching the request category first.
            matching = providers.filter(skill=request_obj.category)
            providers = matching | providers.exclude(skill=request_obj.category)
            self.fields["provider"].label_from_instance = lambda u: (
                f"{u.get_full_name() or u.username} - {u.skill or 'General'}"
                + ("  ✓ matches category" if u.skill == request_obj.category else "")
            )
        self.fields["provider"].queryset = providers.order_by("username")


class StatusUpdateForm(forms.Form):
    status = forms.ChoiceField(choices=[])
    note = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, request_obj, allowed, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            (s.value, ServiceRequest.Status(s).label) for s in allowed
        ]
