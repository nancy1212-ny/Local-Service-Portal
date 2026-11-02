from django.core.management.base import BaseCommand
 
from tracker.models import ServiceRequest, StatusHistory, User
 
S = ServiceRequest.Status
 
# category -> (provider username, [(title, priority), ...])  -- 6 problems each
DEMO_REQUESTS = {
    "Plumbing": ("ravi_plumber", [
        ("Leaking kitchen tap", "high"),
        ("Blocked bathroom drain", "medium"),
        ("Low water pressure in shower", "low"),
        ("Overflowing toilet tank", "high"),
        ("Water heater not heating", "medium"),
        ("Pipe leak under sink", "high"),
    ]),
    "Electrical": ("meena_electric", [
        ("Ceiling fan not working", "medium"),
        ("Power outlet sparking", "high"),
        ("Tube light flickering", "low"),
        ("MCB keeps tripping", "high"),
        ("Install new geyser connection", "medium"),
        ("Doorbell not working", "low"),
    ]),
    "Painting": ("john_painter", [
        ("Repaint living room", "low"),
        ("Touch up bedroom walls", "low"),
        ("Damp patches on ceiling", "medium"),
        ("Paint main door and grills", "medium"),
        ("Exterior wall repaint", "medium"),
        ("Waterproof coat for balcony", "high"),
    ]),
}
 
# What happens to the 1st..6th request of each category.
STAGES = ["pending", "pending", "assigned", "in_progress", "completed", "cancelled"]
 
ADDRESSES = [
    "12 Gandhi Road, Chennai",
    "45 Anna Nagar, Chennai",
    "7 T Nagar Main Street, Chennai",
    "88 Adyar Lane, Chennai",
    "23 Velachery Road, Chennai",
    "5 Mylapore Tank Street, Chennai",
]
 
 
class Command(BaseCommand):
    help = "Create demo users (password: demo12345) and sample requests. Safe to run again."
 
    def handle(self, *args, **opts):
        def mk(username, role, **kw):
            u, created = User.objects.get_or_create(username=username, defaults={"role": role, **kw})
            if created:
                u.set_password("demo12345")
                u.save()
            return u
 
        admin = mk("dispatcher", User.Role.ADMIN, is_staff=True, is_superuser=True, first_name="Dana")
        providers = {
            "ravi_plumber": mk("ravi_plumber", User.Role.PROVIDER, skill="Plumbing", first_name="Ravi"),
            "meena_electric": mk("meena_electric", User.Role.PROVIDER, skill="Electrical", first_name="Meena"),
            "john_painter": mk("john_painter", User.Role.PROVIDER, skill="Painting", first_name="John"),
        }
        customers = [
            mk("asha", User.Role.CUSTOMER, first_name="Asha"),
            mk("kiran", User.Role.CUSTOMER, first_name="Kiran"),
            mk("priya", User.Role.CUSTOMER, first_name="Priya"),
        ]
 
        created = 0
        for category, (provider_name, items) in DEMO_REQUESTS.items():
            provider = providers[provider_name]
            for i, (title, priority) in enumerate(items):
                if ServiceRequest.objects.filter(title=title).exists():
                    continue  # already seeded earlier
                customer = customers[i % len(customers)]
                obj = ServiceRequest.objects.create(
                    title=title, category=category, priority=priority,
                    description=f"{title}. Please send someone as soon as possible.",
                    address=ADDRESSES[i % len(ADDRESSES)], customer=customer,
                )
                StatusHistory.objects.create(
                    request=obj, old_status=S.PENDING, new_status=S.PENDING,
                    changed_by=customer, note="Request created",
                )
                stage = STAGES[i]
                if stage in ("assigned", "in_progress", "completed"):
                    obj.assign_to(provider, admin, "Assigned by dispatcher")
                if stage in ("in_progress", "completed"):
                    obj.change_status(S.IN_PROGRESS, provider, "Reached the site, started work")
                if stage == "completed":
                    obj.change_status(S.COMPLETED, provider, "Work finished")
                if stage == "cancelled":
                    obj.change_status(S.CANCELLED, customer, "Customer no longer needs the service")
                created += 1
 
        self.stdout.write(self.style.SUCCESS(f"Demo data ready ({created} new requests)."))
        self.stdout.write(
            "Logins (password demo12345): dispatcher | ravi_plumber | meena_electric | "
            "john_painter | asha | kiran | priya"
        )
 