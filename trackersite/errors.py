import sys

from django import http
from django.template import TemplateDoesNotExist, loader


# TODO: Remove this override when Django version > 1.9
# Author: proxy https://stackoverflow.com/a/34225705
def permission_denied(request, exception, template_name='403.html'):
    try:
        template = loader.get_template(template_name)
    except TemplateDoesNotExist:
        return http.HttpResponseForbidden('<h1>403 Forbidden</h1>', content_type='text/html')
    return http.HttpResponseForbidden(
        template.render(request=request, context={'exception': exception})
    )
