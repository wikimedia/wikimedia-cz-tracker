# -*- coding: utf-8 -*-
"""
Request every URL that takes no arguments and make sure nothing crashes.

This catches views and templates that break on a new Django or package
version and that no other test renders. It does not check the content of
the pages.
"""
import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.test.client import Client
from django.urls import URLResolver, get_resolver, resolve, Resolver404

from tracker.models import Grant, Topic, Subtopic, Ticket

# Status codes that show the view ran and rendered its response.
# 302: the view redirects, for example a logout or a language switch.
# 405: the view accepts POST only.
ACCEPTABLE_STATUS_CODES = (200, 302, 405)

# URLs that answer with a different status code, with the reason.
EXPECTED_STATUS_CODES = {
    # Each model admin has an autocomplete view. The view answers 404 if the
    # model admin has no search_fields.
    '/admin/tracker/grant/autocomplete/': (404,),
    '/admin/tracker/subtopic/autocomplete/': (404,),
    '/admin/tracker/template/autocomplete/': (404,),
    '/admin/tracker/topic/autocomplete/': (404,),
    '/admin/tracker/trackerprofile/autocomplete/': (404,),
    # The legacy old/ redirect in urls.py has no start anchor. Django 3.0
    # finds old/ at the end of this path and redirects to the web root.
    '/api/tracker/mediainfoold/': (301,),
}

# URLs the test must not request, with the reason.
SKIPPED_URLS = {
    # Proxies the request to the MediaWiki API over the network.
    '/api/mediawiki/',
}


def iter_argless_urls(patterns=None, prefix=''):
    """
    Walk the URL configuration and yield every path that takes no arguments.
    """
    if patterns is None:
        patterns = get_resolver().url_patterns
    for entry in patterns:
        route = str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from iter_argless_urls(entry.url_patterns, prefix + route)
            continue
        candidate = prefix + route
        # Regex patterns: drop the anchors and unescape literal characters.
        candidate = candidate.replace('^', '').replace('$', '')
        candidate = re.sub(r'\\(.)', r'\1', candidate)
        if re.search(r'[()<>\[\]?*+|]', candidate):
            # The pattern takes arguments. Skip it.
            continue
        url = '/' + candidate
        try:
            resolve(url)
        except Resolver404:
            continue
        yield url


class ArglessUrlSmokeTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser('smoke_admin', 'smoke@example.com', 'password')
        grant = Grant.objects.create(full_name='Smoke grant', short_name='smoke', slug='smoke')
        topic = Topic.objects.create(name='Smoke topic', open_for_tickets=True, ticket_media=True, grant=grant)
        Subtopic.objects.create(name='Smoke subtopic', topic=topic)
        Ticket.objects.create(name='Smoke ticket', topic=topic, requested_user=self.superuser)

    def test_url_list_is_not_empty(self):
        urls = list(iter_argless_urls())
        self.assertGreater(len(urls), 40, urls)
        self.assertIn('/tickets/', urls)
        self.assertIn('/admin/tracker/ticket/', urls)
        self.assertIn('/api/', urls)

    def test_every_argless_url_responds(self):
        failures = []
        for url in iter_argless_urls():
            if url in SKIPPED_URLS:
                continue
            # A fresh client per URL. A logout view must not affect the others.
            client = Client()
            client.force_login(self.superuser)
            try:
                response = client.get(url)
            except Exception as e:  # report every crash, whatever its type
                failures.append('%s raised %s: %s' % (url, type(e).__name__, e))
                continue
            expected = EXPECTED_STATUS_CODES.get(url, ACCEPTABLE_STATUS_CODES)
            if response.status_code not in expected:
                failures.append('%s returned %d' % (url, response.status_code))
        self.assertEqual([], failures, '\n'.join(failures))
