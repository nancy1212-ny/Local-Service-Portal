from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import ServiceRequest, StatusHistory, User

S = ServiceRequest.Status


def make_user(username, role, **kw):
    return User.objects.create_user(username=username, password="pass12345", role=role, **kw)


class BaseCase(TestCase):
    def setUp(self):
        self.customer = make_user("cust", User.Role.CUSTOMER)
        self.other_customer = make_user("cust2", User.Role.CUSTOMER)
        self.admin = make_user("boss", User.Role.ADMIN)
        self.plumber = make_user("plumber", User.Role.PROVIDER, skill="Plumbing")
        self.electrician = make_user("sparky", User.Role.PROVIDER, skill="Electrical")
        self.req = ServiceRequest.objects.create(
            title="Leaking tap", description="Kitchen tap leaks", category="Plumbing",
            address="12 Main St", customer=self.customer,
        )


class ModelWorkflowTests(BaseCase):
    def test_assign_pending_request(self):
        self.req.assign_to(self.plumber, self.admin)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, S.ASSIGNED)
        self.assertEqual(self.req.provider, self.plumber)
        self.assertIsNotNone(self.req.assigned_at)
        self.assertEqual(self.req.history.count(), 1)

    def test_cannot_assign_customer_as_provider(self):
        with self.assertRaises(ValidationError):
            self.req.assign_to(self.other_customer, self.admin)

    def test_reassign_keeps_status_and_logs(self):
        self.req.assign_to(self.plumber, self.admin)
        self.req.assign_to(self.electrician, self.admin)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, S.ASSIGNED)
        self.assertEqual(self.req.provider, self.electrician)
        self.assertEqual(self.req.history.count(), 2)

    def test_full_happy_path(self):
        self.req.assign_to(self.plumber, self.admin)
        self.req.change_status(S.IN_PROGRESS, self.plumber)
        self.req.change_status(S.COMPLETED, self.plumber, "Fixed")
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, S.COMPLETED)
        self.assertIsNotNone(self.req.completed_at)
        self.assertEqual(self.req.history.count(), 3)

    def test_invalid_transition_rejected(self):
        with self.assertRaises(ValidationError):
            self.req.change_status(S.COMPLETED, self.admin)  # pending -> completed
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, S.PENDING)

    def test_completed_is_final(self):
        self.req.assign_to(self.plumber, self.admin)
        self.req.change_status(S.IN_PROGRESS, self.plumber)
        self.req.change_status(S.COMPLETED, self.plumber)
        with self.assertRaises(ValidationError):
            self.req.change_status(S.CANCELLED, self.admin)

    def test_provider_decline_returns_to_pending(self):
        self.req.assign_to(self.plumber, self.admin)
        self.req.change_status(S.PENDING, self.plumber, "Can't make it")
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, S.PENDING)
        self.assertIsNone(self.req.provider)
        self.assertIsNone(self.req.assigned_at)


class ViewPermissionTests(BaseCase):
    def test_login_required(self):
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])

    def test_customer_sees_only_own_requests(self):
        ServiceRequest.objects.create(
            title="Other", description="x", category="Other", address="y", customer=self.other_customer
        )
        self.client.login(username="cust", password="pass12345")
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Leaking tap")
        self.assertNotContains(r, ">Other<")

    def test_customer_cannot_view_others_request(self):
        self.client.login(username="cust2", password="pass12345")
        r = self.client.get(reverse("request_detail", args=[self.req.pk]))
        self.assertEqual(r.status_code, 404)

    def test_customer_cannot_assign(self):
        self.client.login(username="cust", password="pass12345")
        r = self.client.post(reverse("assign_request", args=[self.req.pk]), {"provider": self.plumber.pk})
        self.assertEqual(r.status_code, 403)

    def test_admin_assigns_via_view(self):
        self.client.login(username="boss", password="pass12345")
        self.client.post(reverse("assign_request", args=[self.req.pk]), {"provider": self.plumber.pk})
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, S.ASSIGNED)
        self.assertEqual(self.req.provider, self.plumber)

    def test_provider_sees_only_assigned_jobs(self):
        self.client.login(username="plumber", password="pass12345")
        self.assertNotContains(self.client.get(reverse("dashboard")), "Leaking tap")
        self.req.assign_to(self.plumber, self.admin)
        self.assertContains(self.client.get(reverse("dashboard")), "Leaking tap")

    def test_provider_updates_status_via_view(self):
        self.req.assign_to(self.plumber, self.admin)
        self.client.login(username="plumber", password="pass12345")
        self.client.post(reverse("update_status", args=[self.req.pk]), {"status": S.IN_PROGRESS, "note": "On site"})
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, S.IN_PROGRESS)

    def test_other_provider_cannot_update(self):
        self.req.assign_to(self.plumber, self.admin)
        self.client.login(username="sparky", password="pass12345")
        r = self.client.post(reverse("update_status", args=[self.req.pk]), {"status": S.IN_PROGRESS})
        self.assertEqual(r.status_code, 404)  # not visible to them at all

    def test_customer_can_cancel_pending(self):
        self.client.login(username="cust", password="pass12345")
        self.client.post(reverse("update_status", args=[self.req.pk]), {"status": S.CANCELLED})
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, S.CANCELLED)

    def test_customer_creates_request_with_history(self):
        self.client.login(username="cust", password="pass12345")
        self.client.post(reverse("create_request"), {
            "title": "Fan", "category": "Electrical", "priority": "high",
            "address": "5 Lane", "description": "Fan not working",
        })
        obj = ServiceRequest.objects.get(title="Fan")
        self.assertEqual(obj.status, S.PENDING)
        self.assertEqual(StatusHistory.objects.filter(request=obj).count(), 1)

    def test_provider_cannot_create_request(self):
        self.client.login(username="plumber", password="pass12345")
        self.assertEqual(self.client.get(reverse("create_request")).status_code, 403)

    def test_detail_pages_render_for_all_roles(self):
        self.req.assign_to(self.plumber, self.admin)
        for name in ("cust", "boss", "plumber"):
            self.client.login(username=name, password="pass12345")
            self.assertEqual(self.client.get(reverse("request_detail", args=[self.req.pk])).status_code, 200)
