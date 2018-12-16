from datetime import datetime
from random import choice, randint
from pytz import UTC
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db.utils import IntegrityError, DataError
from tracker.models import Grant, Topic, Subtopic, Ticket

USERNAME_PREFIX = "ExampleUser_"
USER_PASSWORD = "ExamplePassword"

ADMINNAME_PREFIX = "AdminUser_"
ADMIN_PASSWORD = USER_PASSWORD


class Command(BaseCommand):
    help = 'Add example data to database.'

    def _create_user(self, name_prefix, name_suffix, password):
        first_names = ["John", "Emilia", "Lisa", "Nathan", "Bob", "Lucas"]
        last_names = ["Smith", "Johnson", "Williams", "Jones", "Garcia", "Miller"]

        return User.objects.create_user(
            name_prefix + str(name_suffix),
            email="{}{}@notreal.example".format(name_prefix, name_suffix),
            password=password,
            first_name=choice(first_names),
            last_name=choice(last_names)
        )

    def generate_and_add_admins(self, amount=4):
        try:
            last_example_admin = User.objects.filter(username__startswith=ADMINNAME_PREFIX).order_by('pk').reverse()[0]
        except IndexError:
            # no example admins
            start_num = 1
        else:
            start_num = int(last_example_admin.username[-1]) + 1
        for n in range(start_num, start_num + amount):
            try:
                self._create_user(ADMINNAME_PREFIX, n, ADMIN_PASSWORD)
            except IntegrityError:
                # Admin already exists.
                pass

    def generate_and_add_users(self, amount=4):
        try:
            last_example_user = User.objects.filter(username__startswith=USERNAME_PREFIX).order_by('pk').reverse()[0]
        except IndexError:
            # no example users
            start_num = 1
        else:
            start_num = int(last_example_user.username[-1]) + 1
        for n in range(start_num, start_num + amount):
            try:
                self._create_user(USERNAME_PREFIX, n, USER_PASSWORD)
            except IntegrityError:
                # User already exists.
                pass

    def generate_and_add_grants(self, amount=4):
        grant_query_list = []
        for n in range(1, amount + 1):
            grant_query_list.append(Grant(
                full_name="Grant number {}".format(n),
                short_name="ExampleG{}".format(n),
                slug="exampleg{}".format(n),
                description=("Detailed grant description. "
                             "Allows for HTML. "
                             "Line breaks are auto parsed.")
            ))
        Grant.objects.bulk_create(grant_query_list)

    def generate_and_add_topics(self, amount=12):
        grant_objects = Grant.objects.all()
        topic_query_list = []
        admins = User.objects.filter(username__startswith=ADMINNAME_PREFIX)
        for n in range(1, amount + 1):
            topic = Topic(
                name="Topic number {}".format(n),
                # This should be fine for selecting grants,
                # since the DB is small if/when you run this command
                grant=choice(grant_objects),
                description=("Detailed topic description. "
                             "Allows for HTML. "
                             "Line breaks are auto parsed."),
                form_description=("This description is"
                                  "shown to users who enter"
                                  "tickets for this topic."),
                open_for_tickets=True,
                ticket_media=True,
                ticket_expenses=True,
                ticket_preexpenses=True,
            )
            if admins.exists():
                topic.save()
                topic.admin.add(choice(admins))
            else:
                topic_query_list.append(topic)

        Topic.objects.bulk_create(topic_query_list)

    def generate_and_add_subtopics(self, amount=20):
        topic_objects = Topic.objects.all()
        subtopic_query_list = []
        for n in range(1, amount + 1):
            subtopic_query_list.append(Subtopic(
                name="Subtopic number {}".format(n),
                description=("Description shown to users who enter "
                             "tickets for this subtopic"),
                topic=choice(topic_objects)

            ))
        Subtopic.objects.bulk_create(subtopic_query_list)

    def generate_and_add_tickets(self, amount=60):
        def generate_random_date():
            year_today = datetime.today().year
            # probably shouldn't matter, but preventing future dates.
            year = randint(year_today - 3, year_today - 1)
            month = randint(1, 12)
            # february only has 28 days, making this harder by
            # including 29-31 is unnecessary
            day = randint(1, 28)
            hour = randint(1, 23)
            minute = randint(1, 59)
            return datetime(year, month, day, hour, minute, tzinfo=UTC)

        user_objects = User.objects.filter(username__startswith=USERNAME_PREFIX)
        if not user_objects.exists():
            raise DataError('To create example tickets, at least one example user has to be created.')
        topic_objects = Topic.objects.all()
        subtopic_objects = Subtopic.objects.all()
        ticket_query_list = []
        for n in range(1, amount + 1):
            created_and_updated = generate_random_date()
            topic = choice(topic_objects)
            try:
                subtopic = choice(subtopic_objects.filter(topic=topic))
            except IndexError:
                # topic has no subtopics
                subtopic = None

            ticket_query_list.append(Ticket(
                created=created_and_updated,
                updated=created_and_updated,
                event_date=generate_random_date(),
                requested_user=choice(user_objects),
                name="Example ticket number {}".format(n),
                topic=topic,
                subtopic=subtopic,
                rating_percentage=randint(0, 100),
                mandatory_report=choice([True, False]),
                description=("Space for further notes. If you're entering a trip "
                             "tell us where did you go and what you did there."),
                supervisor_notes=("This space is for notes of project "
                                  "supervisors and accounting staff."),
            ))
        Ticket.objects.bulk_create(ticket_query_list)

    def add_arguments(self, parser):
        parser.add_argument('--admins', dest='amount_admins', default=4, help='Amount of admins to be generated.')
        parser.add_argument('--users', dest='amount_users', default=4, help='Amount of users to be generated.')
        parser.add_argument('--grants', dest='amount_grants', default=4, help='Amount of grants to be generated.')
        parser.add_argument('--topics', dest='amount_topics', default=12, help='Amount of topics to be generated.')
        parser.add_argument('--subtopics', dest='amount_subtopics', default=20,
                            help='Amount of subtopics to be generated.')
        parser.add_argument('--tickets', dest='amount_tickets', default=60, help='Amount of tickets to be generated.')

        parser.add_argument('--only-generate', dest='only_generate', default=False,
                            help=('Only generate one or multiple types. Takes a lowercase string divided by commas. '
                                  'This option should be used with caution, some types depend on the existence of other'
                                  ' types.'))

        parser.add_argument('--do-not-generate', dest='do_not_generate', default=False,
                            help=('Do not generate one or multiple types. Takes a lowercase string divided by commas. '
                                  'This option should be used with caution, some types depend on the existence of other'
                                  ' types.'))

    def handle(self, **options):
        to_be_generated = ["admins", "users", "grants", "topics", "subtopics", "tickets"]

        if options["only_generate"]:
            to_be_generated = options["only_generate"].split(",")

        if options["do_not_generate"]:
            for item in options["do_not_generate"].split(","):
                to_be_generated.remove(item)

        if "admins" in to_be_generated:
            self.generate_and_add_admins(int(options["amount_admins"]))
        if "users" in to_be_generated:
            self.generate_and_add_users(int(options["amount_users"]))
        if "grants" in to_be_generated:
            self.generate_and_add_grants(int(options["amount_grants"]))
        if "topics" in to_be_generated:
            self.generate_and_add_topics(int(options["amount_topics"]))
        if "subtopics" in to_be_generated:
            self.generate_and_add_subtopics(int(options["amount_subtopics"]))
        if "tickets" in to_be_generated:
            self.generate_and_add_tickets(int(options["amount_tickets"]))
