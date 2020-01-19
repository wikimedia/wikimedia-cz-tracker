import traceback

from django.contrib.sites.models import Site
from django.core.mail import mail_managers
from django.template import loader
from django.urls import reverse
from django.utils.html import strip_tags


def notify_on_failure(**kwargs):
    traceback_text = traceback.format_exc()
    current_site = Site.objects.get_current()
    url = "https://{}{}".format(current_site.domain,
                                reverse("admin:background_task_task_change", args=(kwargs.get("task").id,)))

    template = loader.get_template("admin/failed_background_task_email.html")
    html_content = template.render(context={"traceback": traceback_text,
                                            "task": kwargs.get("task"),
                                            "url": url})
    plain_text_content = strip_tags(html_content)
    mail_managers("Error in background task {}".format(kwargs.get("task")), plain_text_content,
                  html_message=html_content)
