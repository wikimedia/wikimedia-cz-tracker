# -*- coding: utf-8 -*-

import csv
import datetime
import io
import json
import random
import re
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase
from django.test.client import Client
from django.urls import reverse

from tracker.models import Ticket, Topic, Subtopic, Grant, MediaInfo, Expediture, Preexpediture, TrackerProfile, \
    Document, TrackerPreferences
from users.models import UserWrapper


class SimpleTicketTest(TestCase):
    def setUp(self):
        self.topic = Topic(name='topic1', grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        self.topic.save()

        self.ticket1 = Ticket(name='foo', requested_text='req1', topic=self.topic, description='foo foo')
        self.ticket1.save()

        self.ticket2 = Ticket(name='bar', requested_text='req2', topic=self.topic, description='bar bar')
        self.ticket2.save()

    def test_ticket_timestamps(self):
        self.assertTrue(self.ticket2.created > self.ticket1.created)  # check ticket 2 is newer

        # check new update of ticket changed updated ts
        old_updated = self.ticket1.updated
        self.ticket1.description = 'updated description'
        self.ticket1.save()
        self.assertTrue(self.ticket1.updated > old_updated)

    def test_ticket_list(self):
        response = Client().get(reverse('ticket_list'))
        self.assertEqual(response.status_code, 200)

    def test_ticket_json(self):
        for langcode, langname in settings.LANGUAGES:
            response = Client().get(reverse('tickets_json', kwargs={'lang': langcode}))
            self.assertEqual(response.status_code, 200)
            if response.status_code == 200:
                try:
                    json.loads(response.content.decode('utf8'))
                except ValueError:
                    self.fail("Response was not JSON as expected!")

    def test_ticket_detail(self):
        response = Client().get(reverse('ticket_detail', kwargs={'pk': self.ticket1.id}))
        self.assertEqual(response.status_code, 200)

    def test_ticket_absolute_url(self):
        t = self.ticket1
        self.assertEqual(reverse('ticket_detail', kwargs={'pk': t.id}), t.get_absolute_url())

    def test_topic_list(self):
        response = Client().get(reverse('topic_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['topic_list']), 1)

    def test_topic_detail(self):
        response = Client().get(reverse('topic_detail', kwargs={'pk': self.topic.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['topic'].ticket_set.all()), 2)

    def test_topic_absolute_url(self):
        t = self.topic
        self.assertEqual(reverse('topic_detail', kwargs={'pk': t.id}), t.get_absolute_url())

    def _test_one_feed(self, url_name, topic_id, expected_ticket_count):
        url_kwargs = {'pk': topic_id} if topic_id is not None else {}
        response = Client().get(reverse(url_name, kwargs=url_kwargs))
        self.assertEqual(response.status_code, 200)
        items_in_response = re.findall(r'<item>', response.content.decode('utf-8'))  # ugly, mostly works
        self.assertEqual(expected_ticket_count, len(items_in_response))

    def test_feeds(self):
        self.ticket1.add_acks('user_content')
        self._test_one_feed('ticket_list_feed', None, 2)
        self._test_one_feed('ticket_submitted_feed', None, 1)
        self._test_one_feed('topic_ticket_feed', self.topic.id, 2)
        self._test_one_feed('topic_submitted_ticket_feed', self.topic.id, 1)

    def test_historical(self):
        self.ticket1.imported = True
        self.ticket1.save()
        self.assertEqual(self.ticket1.state_str(), 'historical')

    def test_is_completed(self):
        self.assertFalse(self.ticket1.is_completed)
        self.ticket1.add_acks('archive')
        self.assertTrue(self.ticket1.is_completed)
        self.ticket1.ticketack_set.filter(ack_type='archive').delete()
        self.assertFalse(self.ticket1.is_completed)

        self.ticket1.add_acks('close')
        self.assertTrue(self.ticket1.is_completed)
        self.ticket1.ticketack_set.filter(ack_type='close').delete()
        self.assertFalse(self.ticket1.is_completed)


class OldRedirectTests(TestCase):
    def setUp(self):
        self.topic = Topic(name='topic', grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        self.topic.save()
        self.ticket = Ticket(name='foo', requested_text='req', topic=self.topic, description='foo foo')
        self.ticket.save()

    def assert301(self, *args, **kwargs):
        kwargs['status_code'] = 301
        self.assertRedirects(*args, **kwargs)

    def test_old_index(self):
        response = Client().get('/old/')
        self.assert301(response, '/', target_status_code=302)  # 302 = now index is a non-permanent redirect

    def test_topic_index(self):
        response = Client().get('/old/topics/')
        self.assert301(response, reverse('topic_list'))

    def test_ticket(self):
        response = Client().get('/old/ticket/%s/' % self.ticket.id)
        self.assert301(response, self.ticket.get_absolute_url())

    def test_new_ticket(self):
        response = Client().get('/old/ticket/new/')
        self.assert301(response, reverse('create_ticket'), target_status_code=302)  # 302 = redirect to login

    def test_topic(self):
        response = Client().get('/old/topic/%s/' % self.topic.id)
        self.assert301(response, self.topic.get_absolute_url())


class TicketSumTests(TestCase):
    def setUp(self):
        self.topic = Topic(name='topic', grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        self.topic.save()

    def test_empty_ticket(self):
        empty_ticket = Ticket(topic=self.topic, requested_text='someone', name='empty ticket')
        empty_ticket.save()

        self.assertEqual(0, empty_ticket.media_count())
        self.assertEqual(0, empty_ticket.expeditures()['count'])
        self.assertEqual(0, self.topic.media_count())
        self.assertEqual(0, self.topic.expeditures()['count'])

    def test_full_ticket(self):
        full_ticket = Ticket(topic=self.topic, requested_text='someone', name='full ticket')
        full_ticket.save()
        full_ticket.mediainfoold_set.create(description='Vague pictures')
        full_ticket.mediainfoold_set.create(description='Counted pictures', count=15)
        full_ticket.mediainfoold_set.create(description='Even more pictures', count=16)
        full_ticket.mediainfo_set.create(name='test.jpg')
        full_ticket.expediture_set.create(description='Some expense', amount=99)
        full_ticket.expediture_set.create(description='Some other expense', amount=101)
        full_ticket.preexpediture_set.create(description='Preexpediture', amount=99)
        full_ticket.preexpediture_set.create(description='Preexpediture', amount=101)

        self.assertEqual(32, full_ticket.media_count())
        self.assertEqual({'count': 2, 'amount': 200}, full_ticket.expeditures())
        self.assertEqual(32, self.topic.media_count())
        self.assertEqual({'count': 2, 'amount': 200}, self.topic.expeditures())
        self.assertEqual({'count': 2, 'amount': 200}, full_ticket.preexpeditures())


class TicketTests(TestCase):
    def setUp(self):
        self.open_topic = Topic(name='test_topic', open_for_tickets=True, ticket_media=True, grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        self.open_topic.save()

        self.statutory_declaration_topic = Topic(name='statutory_topic', open_for_tickets=True, ticket_media=True, ticket_statutory_declaration=True, grant=Grant.objects.get(short_name='g'))
        self.statutory_declaration_topic.save()

        self.subtopic = Subtopic(name='Test', topic=self.open_topic)
        self.subtopic2 = Subtopic(name='Test2', topic=self.statutory_declaration_topic)
        self.subtopic.save()
        self.subtopic2.save()

        self.password = 'password'
        self.user = User(username='user')
        self.user.set_password(self.password)
        self.user.save()

    def get_client(self):
        c = Client()
        c.login(username=self.user.username, password=self.password)
        return c

    def test_ticket_creation_denied(self):
        response = Client().get(reverse('create_ticket'))
        self.assertEqual(302, response.status_code)  # redirects to login

    def test_ticket_creation(self):
        c = self.get_client()
        response = c.get(reverse('create_ticket'))
        self.assertEqual(200, response.status_code)

        response = c.post(reverse('create_ticket'))
        self.assertEqual(400, response.status_code)

        response = c.post(reverse('create_ticket'), {
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertEqual(200, response.status_code)
        self.assertFormError(response, 'ticketform', 'name', 'This field is required.')
        self.assertFormError(response, 'ticketform', 'deposit', 'This field is required.')

        response = c.post(reverse('create_ticket'), {
            'name': 'ticket',
            'topic': self.statutory_declaration_topic.id,
            'description': 'some desc',
            'deposit': '0',
            'car_travel': True,
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertEqual(200, response.status_code)
        self.assertFormError(response, 'ticketform', 'statutory_declaration', 'You are required to do statutory declaration')

        response = c.post(reverse('create_ticket'), {
            'name': 'ticket',
            'topic': self.open_topic.id,
            'description': 'some desc',
            'deposit': '0',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertEqual(302, response.status_code)
        self.assertEqual(1, Ticket.objects.count())
        ticket = Ticket.objects.order_by('-created')[0]
        self.assertEqual(self.user, ticket.requested_user)
        self.assertEqual(self.user.username, ticket.requested_by())
        self.assertEqual('draft', ticket.state_str())
        self.assertRedirects(response, reverse('ticket_detail', kwargs={'pk': ticket.id}))

    def test_wrong_topic_id(self):
        c = self.get_client()
        response = c.post(reverse('create_ticket'), {
            'name': 'ticket',
            'topic': 'gogo',
            'description': 'some desc',
            'deposit': '0',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertEqual(200, response.status_code)
        self.assertFormError(response, 'ticketform', 'topic', 'Select a valid choice. That choice is not one of the available choices.')

    def test_closed_topic(self):
        closed_topic = Topic(name='closed topic', open_for_tickets=False, grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        closed_topic.save()

        c = self.get_client()
        response = c.post(reverse('create_ticket'), {
            'name': 'ticket',
            'topic': closed_topic.id,
            'description': 'some desc',
            'deposit': '0',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertEqual(200, response.status_code)
        self.assertFormError(response, 'ticketform', 'topic', 'Select a valid choice. That choice is not one of the available choices.')

    def test_too_big_deposit(self):
        c = self.get_client()
        response = c.post(reverse('create_ticket'), {
            'name': 'ticket',
            'topic': self.open_topic.id,
            'description': 'some desc',
            'deposit': '100',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertEqual(200, response.status_code)
        self.assertFormError(response, 'ticketform', 'deposit', 'Your deposit is bigger than your preexpeditures')

    def test_too_big_deposit2(self):
        c = self.get_client()
        response = c.post(reverse('create_ticket'), {
            'name': 'ticket',
            'topic': self.open_topic.id,
            'description': 'some desc',
            'deposit': '50.01',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '1',
            'preexpediture-0-description': 'foo',
            'preexpediture-0-amount': '50',
        })
        self.assertEqual(200, response.status_code)
        self.assertFormError(response, 'ticketform', 'deposit', 'Your deposit is bigger than your preexpeditures')

    def test_invalid_subtopic(self):
        c = self.get_client()
        response = c.post(reverse('create_ticket'), {
            'name': 'ticket',
            'topic': self.open_topic.id,
            'subtopic': self.subtopic2.id,
            'description': 'some desc',
            'deposit': '0',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertEqual(200, response.status_code)
        self.assertFormError(response, 'ticketform', 'subtopic', 'Subtopic must belong to the topic you used. You probably have JavaScript turned off.')

    def test_valid_subtopic(self):
        c = self.get_client()
        response = c.post(reverse('create_ticket'), {
            'name': 'ticket',
            'topic': self.open_topic.id,
            'subtopic': self.subtopic.id,
            'description': 'some desc',
            'deposit': '0',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertEqual(302, response.status_code)
        ticket = Ticket.objects.order_by('-created')[0]
        self.assertRedirects(response, reverse('ticket_detail', kwargs={'pk': ticket.id}))

    def test_correct_deposit(self):
        c = self.get_client()
        response = c.post(reverse('create_ticket'), {
            'name': 'ticket',
            'topic': self.open_topic.id,
            'description': 'some desc',
            'deposit': '30.1',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '2',
            'preexpediture-0-description': 'pre1',
            'preexpediture-0-amount': '10.0',
            'preexpediture-1-description': 'pre2',
            'preexpediture-1-amount': '20.1',
            'preexpediture-1-wage': 'true',
        })
        self.assertEqual(302, response.status_code)
        self.assertEqual(1, Ticket.objects.count())
        ticket = Ticket.objects.order_by('-created')[0]
        self.assertEqual(Decimal('30.1'), ticket.deposit)

        preexpeditures = ticket.preexpediture_set.order_by('description')
        self.assertEqual(2, len(preexpeditures))
        self.assertEqual('pre1', preexpeditures[0].description)
        self.assertEqual(Decimal(10), preexpeditures[0].amount)
        self.assertEqual(False, preexpeditures[0].wage)
        self.assertEqual('pre2', preexpeditures[1].description)
        self.assertEqual(Decimal('20.1'), preexpeditures[1].amount)
        self.assertEqual(True, preexpeditures[1].wage)


class TicketEditTests(TestCase):
    def setUp(self):
        self.topic = Topic(name='topic', grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        self.topic.save()

        self.statutory_topic = Topic(name='statutory_topic', ticket_statutory_declaration=True, grant=Grant.objects.get(short_name='g'))
        self.statutory_topic.save()

        self.subtopic = Subtopic(name='subtopic', topic=self.topic)
        self.subtopic2 = Subtopic(name='subtopic2', topic=self.statutory_topic)
        self.subtopic.save()
        self.subtopic2.save()

        self.password = 'my_password'
        self.user = User(username='my_user')
        self.user.set_password(self.password)
        self.user.save()

    def test_correct_choices(self):
        grant = Grant.objects.create(full_name='g', short_name='g', slug='g')
        t_closed = Topic(name='t1', open_for_tickets=False, grant=grant)
        t_closed.save()
        t_open = Topic(name='t2', open_for_tickets=True, grant=grant)
        t_open.save()
        t_assigned = Topic(name='t3', open_for_tickets=False, grant=grant)
        t_assigned.save()
        ticket = Ticket(name='ticket', topic=t_assigned)
        ticket.save()

        from tracker.views import get_edit_ticket_form_class
        EditForm = get_edit_ticket_form_class(ticket)
        choices = {t.id for t in EditForm().fields['topic'].queryset.all()}
        wanted_choices = {t_open.id, t_assigned.id, self.topic.id, self.statutory_topic.id}
        self.assertEqual(wanted_choices, choices)

    def test_ticket_edit_anonymous(self):
        ticket = Ticket(name='ticket', topic=self.topic, requested_user=None, requested_text='foo')
        ticket.save()
        ticket.add_acks('close')

        c = Client()
        response = c.get(reverse('edit_ticket', kwargs={'pk': ticket.id}))
        self.assertEqual(302, response.status_code)  # should be redirect to login page

    def test_ticket_edit_not_owned(self):
        ticket = Ticket(name='ticket', topic=self.topic, requested_user=None, requested_text='foo')
        ticket.save()
        ticket.add_acks('close')

        c = Client()
        c.login(username=self.user.username, password=self.password)
        response = c.get(reverse('edit_ticket', kwargs={'pk': ticket.id}))
        self.assertEqual(403, response.status_code)  # denies edit of non-own ticket

    def test_ticket_edit_locked(self):
        ticket = Ticket(name='ticket', topic=self.topic, requested_user=self.user)
        ticket.save()
        ticket.add_acks('close')

        c = Client()
        c.login(username=self.user.username, password=self.password)

        response = c.get(reverse('edit_ticket', kwargs={'pk': ticket.id}))
        self.assertEqual(403, response.status_code)  # still deny edit, ticket locked

    def test_ticket_edit_loaded(self):
        ticket = Ticket(name='ticket', topic=self.topic, requested_user=self.user)
        ticket.save()

        c = Client()
        c.login(username=self.user.username, password=self.password)

        response = c.get(reverse('edit_ticket', kwargs={'pk': ticket.id}))
        self.assertEqual(200, response.status_code)  # now it should pass

    def test_ticket_edit_submit(self):
        ticket = Ticket(name='ticket', topic=self.topic, requested_user=self.user)
        ticket.save()

        c = Client()
        c.login(username=self.user.username, password=self.password)

        # try to submit the form
        response = c.post(reverse('edit_ticket', kwargs={'pk': ticket.id}), {
            'name': 'new name',
            'topic': ticket.topic.id,
            'description': 'new desc',
            'deposit': '0',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertRedirects(response, reverse('ticket_detail', kwargs={'pk': ticket.id}))

        # check changed ticket data
        ticket = Ticket.objects.get(id=ticket.id)
        self.assertEqual(self.user, ticket.requested_user)
        self.assertEqual('new name', ticket.name)
        self.assertEqual('new desc', ticket.description)

    def test_ticket_edit_expediture_broken(self):
        ticket = Ticket(name='ticket', topic=self.topic, requested_user=self.user)
        ticket.save()

        c = Client()
        c.login(username=self.user.username, password=self.password)

        # b0rked expediture items aborts the submit
        response = c.post(reverse('edit_ticket', kwargs={'pk': ticket.id}), {
            'name': 'ticket',
            'topic': ticket.topic.id,
            'description': 'some desc',
            'deposit': '0',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '1',
            'expediture-0-description': 'foo',
            'expediture-0-amount': '',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual('This field is required.', response.context['expeditures'].forms[0].errors['amount'][0])

    def test_ticket_edit_expediture_okay(self):
        ticket = Ticket(name='ticket', topic=self.topic, requested_user=self.user)
        ticket.save()

        c = Client()
        c.login(username=self.user.username, password=self.password)
        response = c.get(reverse('edit_ticket', kwargs={'pk': ticket.id}))
        self.assertEqual(response.status_code, 200)

        # add some inline items
        response = c.post(reverse('edit_ticket', kwargs={'pk': ticket.id}), {
            'name': 'new name',
            'topic': ticket.topic.id,
            'description': 'new desc',
            'deposit': '0',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '2',
            'expediture-0-description': 'ten fifty',
            'expediture-0-amount': '10.50',
            'expediture-1-description': 'hundred',
            'expediture-1-amount': '100',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertRedirects(response, reverse('ticket_detail', kwargs={'pk': ticket.id}))
        expeditures = ticket.expediture_set.order_by('amount')
        self.assertEqual(2, len(expeditures))
        self.assertEqual('ten fifty', expeditures[0].description)
        self.assertEqual(10.5, expeditures[0].amount)
        self.assertEqual('hundred', expeditures[1].description)
        self.assertEqual(100, expeditures[1].amount)

        # edit inline items
        response = c.post(reverse('edit_ticket', kwargs={'pk': ticket.id}), {
            'name': 'new name',
            'topic': ticket.topic.id,
            'description': 'new desc',
            'deposit': '0',
            'expediture-INITIAL_FORMS': '2',
            'expediture-TOTAL_FORMS': '3',
            'expediture-0-id': expeditures[0].id,
            'expediture-0-description': 'ten fifty',
            'expediture-0-amount': '10.50',
            'expediture-0-DELETE': 'on',
            'expediture-1-id': expeditures[1].id,
            'expediture-1-description': 'hundred+1',
            'expediture-1-amount': '101',
            'expediture-2-description': '',
            'expediture-2-amount': '',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertRedirects(response, reverse('ticket_detail', kwargs={'pk': ticket.id}))
        expeditures = ticket.expediture_set.order_by('amount')
        self.assertEqual(1, len(expeditures))
        self.assertEqual('hundred+1', expeditures[0].description)
        self.assertEqual(101, expeditures[0].amount)

    def test_ticket_edit_precontent_preexpeditures_ignored(self):
        ticket = Ticket(name='ticket', topic=self.topic, requested_user=self.user)
        ticket.save()

        c = Client()
        c.login(username=self.user.username, password=self.password)

        # add preexpeditures, and amount flag preack
        deposit_amount = Decimal('12324.37')
        ticket = Ticket.objects.get(id=ticket.id)
        ticket.deposit = deposit_amount
        ticket.preexpediture_set.create(description='some preexp', amount=15)
        ticket.save()
        ticket.add_acks('precontent')

        # edit should work and ignore new data
        response = c.get(reverse('edit_ticket', kwargs={'pk': ticket.id}))
        self.assertEqual(response.status_code, 200)

        response = c.post(reverse('edit_ticket', kwargs={'pk': ticket.id}), {
            'name': 'new name',
            'topic': ticket.topic.id,
            'description': 'new desc',
            'deposit': '333',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '0',
        })
        self.assertRedirects(response, reverse('ticket_detail', kwargs={'pk': ticket.id}))
        ticket = Ticket.objects.get(id=ticket.id)
        self.assertEqual(deposit_amount, ticket.deposit)
        self.assertEqual(1, ticket.preexpediture_set.count())

    def test_ticket_edit_precontent_no_preexpeditures(self):
        ticket = Ticket(name='ticket', topic=self.topic, requested_user=self.user)
        ticket.save()

        c = Client()
        c.login(username=self.user.username, password=self.password)
        ticket.preexpediture_set.create(description='test', amount=15)
        ticket.save()
        ticket.add_acks('precontent')

        # also, edit should work and not fail on missing preack-ignored fields
        response = c.get(reverse('edit_ticket', kwargs={'pk': ticket.id}))
        self.assertEqual(response.status_code, 200)

        response = c.post(reverse('edit_ticket', kwargs={'pk': ticket.id}), {
            'name': 'new name',
            'topic': ticket.topic.id,
            'description': 'new desc',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
        })
        self.assertRedirects(response, reverse('ticket_detail', kwargs={'pk': ticket.id}))
        ticket = Ticket.objects.get(id=ticket.id)
        self.assertEqual(1, ticket.preexpediture_set.count())


class TicketAckTests(TestCase):
    def setUp(self):
        self.grant = Grant.objects.create(full_name='g', short_name='g', slug='g')
        self.topic = Topic.objects.create(name='t', grant=self.grant)
        self.password = 'my_password'
        self.user = User(username='my_user')
        self.user.set_password(self.password)
        self.user.save()
        self.ticket = Ticket.objects.create(name='ticket', topic=self.topic, requested_user=self.user)

    def test_ack_user_edit(self):
        # two user acks are possible
        self.assertEqual(
            {'user_precontent', 'user_content', 'user_docs'},
            {a.ack_type for a in self.ticket.possible_user_acks()}
        )

        # add some acks, now only user_content is possible to add
        self.ticket.add_acks('user_docs', 'user_precontent')
        self.assertEqual(
            {'user_content'},
            {a.ack_type for a in self.ticket.possible_user_acks()}
        )

        # user_docs can be removed
        ud = self.ticket.ticketack_set.get(ack_type='user_docs')
        self.assertTrue(ud.user_removable)

        # content can't be removed
        self.ticket.add_acks('content')
        cont = self.ticket.ticketack_set.get(ack_type='content')
        self.assertFalse(cont.user_removable)

    def test_ack_user_add(self):
        c = Client()
        c.login(username=self.user.username, password=self.password)
        add_url = reverse('ticket_ack_add', kwargs={
            'pk': self.ticket.id,
            'ack_type': 'user_content'
        })
        response = c.get(add_url)
        self.assertEqual(response.status_code, 200)

        response = c.post(add_url)
        self.assertRedirects(response, reverse('ticket_detail', kwargs={'pk': self.ticket.id}))
        self.assertTrue('user_content' in self.ticket.ack_set())

    def test_ack_user_delete(self):
        self.ticket.add_acks('user_docs')
        ud = self.ticket.ticketack_set.get(ack_type='user_docs')

        c = Client()
        c.login(username=self.user.username, password=self.password)
        delete_url = reverse('ticket_ack_delete', kwargs={'pk': self.ticket.id, 'ack_id': ud.id})
        response = c.get(delete_url)
        self.assertEqual(response.status_code, 200)

        response = c.post(delete_url)
        self.assertRedirects(response, reverse('ticket_detail', kwargs={'pk': self.ticket.id}))
        self.assertTrue('user_docs' not in self.ticket.ack_set())

    def test_ack_not_deletable_by_anon(self):
        self.ticket.add_acks('user_docs')
        ud = self.ticket.ticketack_set.get(ack_type='user_docs')

        c = Client()
        response = c.post(reverse('ticket_ack_delete', kwargs={'pk': self.ticket.id, 'ack_id': ud.id}))
        self.assertEqual(response.status_code, 403)

    def test_ack_not_deletable_when_admin_only(self):
        self.ticket.add_acks('content')
        cont = self.ticket.ticketack_set.get(ack_type='content')

        c = Client()
        c.login(username=self.user.username, password=self.password)
        response = c.post(reverse('ticket_ack_delete', kwargs={'pk': self.ticket.id, 'ack_id': cont.id}))
        self.assertEqual(response.status_code, 403)

    def test_topic_content_acks_per_user(self):
        c = Client()
        response = c.get(reverse('topic_content_acks_per_user'))
        self.assertEqual(response.status_code, 200)

    def test_topic_content_acks_per_user_csv(self):
        c = Client()
        response = c.get(reverse('topic_content_acks_per_user_csv'))
        self.assertEqual(response.status_code, 200)

    def test_ack_not_submittable_by_anon(self):
        c = Client()
        add_url = reverse('ticket_ack_add', kwargs={
            'pk': self.ticket.id,
            'ack_type': 'user_content'
        })
        response = c.get(add_url)
        self.assertEqual(response.status_code, 403)

        response = c.post(add_url)
        self.assertEqual(response.status_code, 403)

    def test_ack_add_with_comment(self):
        c = Client()
        c.login(username=self.user.username, password=self.password)

        add_url = reverse('ticket_ack_add', kwargs={
            'pk': self.ticket.id,
            'ack_type': 'user_content'
        })

        c.post(add_url, {
            'comment': 'test_comment'
        })
        ack = self.ticket.ticketack_set.get(ack_type='user_content')
        self.assertEqual('test_comment', ack.comment)

    def test_ack_not_submittable_when_archived(self):
        c = Client()
        c.login(username=self.user.username, password=self.password)
        self.ticket.add_acks('archive')

        add_url = reverse('ticket_ack_add', kwargs={
            'pk': self.ticket.id,
            'ack_type': 'user_content'
        })
        response = c.get(add_url)
        self.assertEqual(response.status_code, 403)

        response = c.post(add_url)
        self.assertEqual(response.status_code, 403)


class TicketEditLinkTests(TestCase):
    def setUp(self):
        self.topic = Topic(name='topic', grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        self.topic.save()

        self.password = 'my_password'
        self.user = User(username='my_user')
        self.user.set_password(self.password)
        self.user.save()

        self.ticket = Ticket(name='ticket', topic=self.topic, requested_user=None, requested_text='foo')
        self.ticket.save()

    def get_ticket_response(self):
        c = Client()
        c.login(username=self.user.username, password=self.password)
        response = c.get(reverse('ticket_detail', kwargs={'pk': self.ticket.id}))
        self.assertEqual(response.status_code, 200)
        return response

    def test_clear_ticket(self):
        response = self.get_ticket_response()
        self.assertEqual(False, response.context['user_can_edit_ticket'])
        self.assertEqual(False, response.context['user_can_edit_ticket_in_admin'])

    def test_own_ticket(self):
        self.ticket.requested_user = self.user
        self.ticket.save()
        response = self.get_ticket_response()
        self.assertEqual(True, response.context['user_can_edit_ticket'])
        self.assertEqual(False, response.context['user_can_edit_ticket_in_admin'])

    def test_bare_admin(self):
        self.user.is_staff = True
        self.user.save()
        response = self.get_ticket_response()
        self.assertEqual(False, response.context['user_can_edit_ticket'])
        self.assertEqual(False, response.context['user_can_edit_ticket_in_admin'])

    def test_tracker_supervisor(self):
        self.user.is_staff = True
        topic_content = ContentType.objects.get(app_label='tracker', model='Topic')
        self.user.user_permissions.add(Permission.objects.get(content_type=topic_content, codename='supervisor'))
        self.user.save()

        response = self.get_ticket_response()
        self.assertEqual(False, response.context['user_can_edit_ticket'])
        self.assertEqual(True, response.context['user_can_edit_ticket_in_admin'])

    def test_total_supervisor(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

        response = self.get_ticket_response()
        self.assertEqual(False, response.context['user_can_edit_ticket'])
        self.assertEqual(True, response.context['user_can_edit_ticket_in_admin'])

    def test_own_topic(self):
        self.user.is_staff = True
        self.user.topic_set.add(self.topic)
        self.user.save()

        response = self.get_ticket_response()
        self.assertEqual(False, response.context['user_can_edit_ticket'])
        self.assertEqual(True, response.context['user_can_edit_ticket_in_admin'])


class UserDetailsTest(TestCase):
    def setUp(self):
        self.topic = Topic(name='test_topic', open_for_tickets=True, ticket_media=True, grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        self.topic.save()

        self.user = User(username='user')
        self.user.save()

        self.ticket = Ticket(name='foo', requested_user=self.user, topic=self.topic, description='foo foo')
        self.ticket.save()

    def test_user_details(self):
        c = Client()
        response = c.get(UserWrapper(self.user).get_absolute_url())
        self.assertEqual(200, response.status_code)
        self.assertEqual(self.ticket, response.context['ticket_list'][0])


class SummaryTest(TestCase):
    def setUp(self):
        self.user = User(username='user')
        self.user.save()

        self.topic = Topic(name='test_topic', ticket_expenses=True, grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        self.topic.save()

        self.ticket = Ticket(name='foo', requested_user=self.user, topic=self.topic, rating_percentage=50)
        self.ticket.save()
        self.ticket.add_acks('content', 'docs', 'archive')
        self.ticket.expediture_set.create(description='foo', amount=200)
        self.ticket.expediture_set.create(description='foo', amount=100)
        self.ticket.mediainfoold_set.create(description='foo', count=5)
        self.ticket.mediainfo_set.create(name='test.jpg')
        self.ticket.mediainfo_set.create(name='test2.jpg')

        self.ticket2 = Ticket(name='foo', requested_user=self.user, topic=self.topic, rating_percentage=100)
        self.ticket2.save()
        self.ticket2.add_acks('content', 'docs', 'archive')
        self.ticket2.expediture_set.create(description='foo', amount=600)
        self.ticket2.expediture_set.create(description='foo', amount=10)
        self.ticket2.mediainfoold_set.create(description='foo', count=5)
        self.ticket2.mediainfoold_set.create(description='foo', count=3)
        self.ticket2.mediainfo_set.create(name='test.jpg')

    def test_topic_ticket_counts(self):
        self.assertEqual({'unpaid': 2}, self.topic.tickets_per_payment_status())
        for e in self.ticket.expediture_set.all():
            e.paid = True
            e.save()
        self.assertEqual({'unpaid': 1, 'paid': 1}, self.topic.tickets_per_payment_status())

    def test_topic_ticket_counts2(self):
        """ change event_date (and thus sort_date) of one ticket, make sure it
            does not break grouping
        """
        self.ticket.event_date = datetime.date(2016, 1, 1)
        self.ticket.save()
        self.assertEqual({'unpaid': 2}, self.topic.tickets_per_payment_status())

    def test_ticket_name(self):
        self.ticket.ticketack_set.filter(ack_type='content').delete()
        self.ticket.rating_percentage = None
        self.ticket.save()

        self.assertEqual(7, self.ticket.media_count())
        self.assertEqual({'objects': 1, 'media': 5}, self.ticket.media_old_count())
        self.assertEqual({'count': 2, 'amount': 300}, self.ticket.expeditures())
        self.assertEqual(0, self.ticket.accepted_expeditures())

        self.ticket.rating_percentage = 50
        self.ticket.save()
        self.assertEqual(0, self.ticket.accepted_expeditures())

        self.ticket.add_acks('content')
        self.assertEqual(150, self.ticket.accepted_expeditures())

    def test_topic_name(self):
        self.assertEqual(16, self.topic.media_count())
        self.assertEqual({'count': 4, 'amount': 910}, self.topic.expeditures())
        self.assertEqual(150 + 610, self.topic.accepted_expeditures())

    def test_user_name(self):
        profile = self.user.trackerprofile
        self.assertEqual(16, profile.media_count())
        self.assertEqual(150 + 610, profile.accepted_expeditures())

    def test_topic_finance(self):
        response = Client().get(reverse('topic_finance'))
        self.assertEqual(response.status_code, 200)


class UserProfileTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create(username='simpleuser')
        self.user2 = User.objects.create(username='simple_user5547')
        self.user3 = User.objects.create(username='simple_user_5547@+.-')

    def test_simple_create(self):
        user = User.objects.create(username='new_user')
        try:
            user.trackerprofile
        except TrackerProfile.DoesNotExist:
            self.fail('Failed to create trackerprofile for new user')

    def test_profile_route(self):
        response = Client().get(reverse('user_list'))
        self.assertEqual(200, response.status_code)

    def test_user_profile_load(self):
        c = Client()
        response = c.get(UserWrapper(self.user1).get_absolute_url())
        self.assertEqual(200, response.status_code)

        response = c.get(UserWrapper(self.user2).get_absolute_url())
        self.assertEqual(200, response.status_code)

        response = c.get(UserWrapper(self.user3).get_absolute_url())
        self.assertEqual(200, response.status_code)


class ImportTests(TestCase):

    def get_test_data(self, type):
        csvfile = io.StringIO()
        csvwriter = csv.writer(csvfile, delimiter=';')
        if type == 'ticket':
            csvwriter.writerow(['event_date', 'name', 'topic', 'event_url', 'description', 'deposit'])
            csvwriter.writerow([u'2010-04-23', u'Nazev ticketu', u'Nazev tematu', u'http://wikimedia.cz', u'Popis ticketu', u'0'])
        elif type == 'topic':
            csvwriter.writerow(['name', 'grant', 'open_for_new_tickets', 'media', 'preexpenses', 'expenses', 'description', 'form_description'])
            csvwriter.writerow([u'Nazev tematu', u'Nazev grantu', u'True', u'True', u'True', u'True', u'Popis tematu', u'Popis formulare tematu'])
        elif type == 'grant':
            csvwriter.writerow(['full_name', 'short_name', 'slug', 'description'])
            csvwriter.writerow([u'Nazev grantu', u'grant', u'grant', u'Popis'])
        elif type == 'user':
            csvwriter.writerow(['username', 'password', 'first_name', 'last_name', 'is_superuser', 'is_staff', 'is_active', 'email'])
            csvwriter.writerow([u'username', u'Heslo', u'name', u'surname', u'False', u'False', u'True', u'emailova@adresa.cz'])
        elif type == 'media':
            csvwriter.writerow(['ticket_id', 'url', 'description', 'number'])
            csvwriter.writerow(['1', 'http://wikimedia.cz', 'popis', '1'])
        elif type == 'expense':
            csvwriter.writerow(['ticket_id', 'description', 'amount', 'wage', 'accounting_info', 'paid'])
            csvwriter.writerow(['1', 'popisek', '100', True, 'accounting info', False])
        elif type == 'preexpense':
            csvwriter.writerow(['ticket_id', 'description', 'amount', 'wage'])
            csvwriter.writerow(['1', 'popisek', '100', True])
        csvfile.seek(0)
        return csvfile

    def reset_attempt(self, type):
        if type == 'ticket':
            for t in Ticket.objects.all():
                t.delete()
        if type == 'topic':
            for t in Topic.objects.all():
                t.delete()
        if type == 'grant':
            for t in Grant.objects.all():
                t.delete()
        if type == 'user':
            for t in User.objects.exclude(username='user').exclude(username='staffer').exclude(username='superuser'):
                t.delete()
        if type == 'media':
            for t in MediaInfo.objects.all():
                t.delete()
        if type == 'expense':
            for t in Expediture.objects.all():
                t.delete()
        if type == 'preexpense':
            for t in Preexpediture.objects.all():
                t.delete()

    def test_access_rights(self):
        user = {'user': User.objects.create(username='user'), 'password': 'pw1'}
        staffer = {'user': User.objects.create(username='staffer', is_staff=True), 'password': 'pw2'}
        superuser = {'user': User.objects.create(username='superuser', is_staff=True, is_superuser=True), 'password': 'pw3'}
        for u in (user, staffer, superuser):
            u['user'].set_password(u['password'])
            u['user'].save()
        testConfigurations = [
            {
                'type': 'grant',
                'normal': 403,
                'staffer': 302,
                'superuser': 302,
            },
            {
                'type': 'topic',
                'normal': 403,
                'staffer': 302,
                'superuser': 302,
            },
            {
                'type': 'user',
                'normal': 403,
                'staffer': 403,
                'superuser': 302,
            },
            {
                'type': 'ticket',
                'normal': 302,
                'staffer': 302,
                'superuser': 302
            },
        ]
        for testConfiguration in testConfigurations:
            c = Client()
            c.login(username=user['user'].username, password=user['password'])  # Login with normal user account
            response = c.post(reverse('importcsv'), {
                'type': testConfiguration['type'],
                'csvfile': self.get_test_data(testConfiguration['type'])
            })
            self.assertEqual(testConfiguration['normal'], response.status_code)
            self.reset_attempt(testConfiguration['type'])
            c = Client()
            c.login(username=staffer['user'].username, password=staffer['password'])  # Login with staffer user account
            response = c.post(reverse('importcsv'), {
                'type': testConfiguration['type'],
                'csvfile': self.get_test_data(testConfiguration['type'])
            })
            self.assertEqual(testConfiguration['staffer'], response.status_code)
            self.reset_attempt(testConfiguration['type'])
            c = Client()
            c.login(username=superuser['user'].username, password=superuser['password'])  # Login with superuser user account
            response = c.post(reverse('importcsv'), {
                'type': testConfiguration['type'],
                'csvfile': self.get_test_data(testConfiguration['type'])
            })
            self.assertEqual(testConfiguration['superuser'], response.status_code)


class ExportTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.password = 'user_password'
        self.standardUser = User.objects.create_user(username='standard_user', password=self.password)
        self.staffUser = User.objects.create_user(username='staff_user', password=self.password)
        self.staffUser.is_staff = True
        self.staffUser.save()
        self.superuser = User.objects.create_superuser(username='superuser', password=self.password, email='test@test')

        self.grant1 = Grant.objects.create(full_name='g1full', short_name='g1short')
        self.grant2 = Grant.objects.create(full_name='g2full', short_name='g2short')

        self.topic1 = Topic.objects.create(name='t1', grant=self.grant1)
        self.topic2 = Topic.objects.create(name='t2', grant=self.grant2)

        self.ticket1 = Ticket.objects.create(name='t1', topic=self.topic1, requested_user=self.standardUser)
        self.ticket2 = Ticket.objects.create(name='t2', topic=self.topic2, requested_user=self.standardUser, mandatory_report=True)

        self.preexpeditureWithWage1 = Preexpediture.objects.create(ticket=self.ticket1, description='t1', amount='22', wage=True)
        self.preexpeditureWithWage2 = Preexpediture.objects.create(ticket=self.ticket1, description='t2', amount='23', wage=True)
        self.preexpeditureWithoutWage = Preexpediture.objects.create(ticket=self.ticket2, description='f', amount='24', wage=False)

        self.expeditureWithWagePaid1 = Expediture.objects.create(ticket=self.ticket1, description='tt1', amount='32', accounting_info='', wage=True, paid=True)
        self.expeditureWithWagePaid2 = Expediture.objects.create(ticket=self.ticket1, description='tt2', amount='33', accounting_info='', wage=True, paid=True)
        self.expeditureWithoutWagePaid = Expediture.objects.create(ticket=self.ticket2, description='ff', amount='34', accounting_info='', wage=False, paid=False)

    def read_csv(self, csvContent):
        result = []
        content = csv.reader(io.StringIO(csvContent.decode('utf-8')))
        for row in content:
            result.append(row[0].replace('\"', '').split(';'))
        return result

    def test_export_tickets(self):
        # Request without ticket-report-mandatory property
        # In this case, the system will return all tickets from the database
        response = self.client.post(reverse('export'), {
            'type': 'ticket',
            'preexpeditures-larger': '',
            'preexpeditures-smaller': '',
            'expeditures-larger': '',
            'expeditures-smaller': '',
            'acceptedexpeditures-larger': '',
            'acceptedexpeditures-smaller': ''
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 2)
        self.assertEqual(csvContent[1][0], str(self.ticket1.id))
        self.assertEqual(csvContent[2][0], str(self.ticket2.id))

        # Request with ticket-report-mandatory property
        # In this case, the system will return only tickets which have mandatory_report property enabled
        response = self.client.post(reverse('export'), {
            'type': 'ticket',
            'preexpeditures-larger': '',
            'preexpeditures-smaller': '',
            'expeditures-larger': '',
            'expeditures-smaller': '',
            'acceptedexpeditures-larger': '',
            'acceptedexpeditures-smaller': '',
            'ticket-report-mandatory': ''
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 1)
        self.assertEqual(csvContent[1][0], str(self.ticket2.id))
        self.assertEqual(csvContent[1][13], str(self.ticket2.mandatory_report))

    def test_export_grants(self):
        response = self.client.post(reverse('export'), {
            'type': 'grant'
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 2)

    def test_export_preexpeditures(self):
        # Request with preexpediture-wage property
        response = self.client.post(reverse('export'), {
            'type': 'preexpediture',
            'preexpediture-amount-larger': '',
            'preexpediture-wage': ''
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 2)
        self.assertEqual(csvContent[1][0], str(self.ticket1.id))
        self.assertEqual(csvContent[1][3], str(self.preexpeditureWithWage1.wage))

        self.assertEqual(csvContent[2][0], str(self.ticket1.id))
        self.assertEqual(csvContent[2][3], str(self.preexpeditureWithWage2.wage))

        # Request without preexpediture-wage property
        response = self.client.post(reverse('export'), {
            'type': 'preexpediture',
            'preexpediture-amount-larger': ''
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 1)
        self.assertEqual(csvContent[1][0], str(self.ticket2.id))
        self.assertEqual(csvContent[1][3], str(self.expeditureWithoutWagePaid.wage))

    def test_export_expeditures(self):
        # Request with expediture-wage and expediture-paid properties
        response = self.client.post(reverse('export'), {
            'type': 'expediture',
            'expediture-amount-larger': '',
            'expediture-amount-smaller': '',
            'expediture-wage': '',
            'expediture-paid': ''
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 2)
        self.assertEqual(csvContent[1][0], str(self.ticket1.id))
        self.assertEqual(csvContent[1][3], str(self.expeditureWithWagePaid1.wage))
        self.assertEqual(csvContent[1][4], str(self.expeditureWithWagePaid1.paid))

        self.assertEqual(csvContent[2][0], str(self.ticket1.id))
        self.assertEqual(csvContent[2][3], str(self.expeditureWithWagePaid2.wage))
        self.assertEqual(csvContent[2][4], str(self.expeditureWithWagePaid2.paid))

        # Request without expediture-wage and expediture-paid properties
        response = self.client.post(reverse('export'), {
            'type': 'expediture',
            'expediture-amount-larger': '',
            'expediture-amount-smaller': ''
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 1)
        self.assertEqual(csvContent[1][0], str(self.ticket2.id))
        self.assertEqual(csvContent[1][3], str(self.expeditureWithoutWagePaid.wage))
        self.assertEqual(csvContent[1][4], str(self.expeditureWithoutWagePaid.paid))

    def test_export_topics(self):
        # Request with default value of topics-paymentstate property
        response = self.client.post(reverse('export'), {
            'type': 'topic',
            'topics-tickets-larger': '',
            'topics-tickets-smaller': '',
            'topics-paymentstate': 'default'
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 2)
        self.assertEqual(csvContent[1][0], str(self.topic1.name))
        self.assertEqual(csvContent[1][1], str(self.grant1.full_name))

        self.assertEqual(csvContent[2][0], str(self.topic2.name))
        self.assertEqual(csvContent[2][1], str(self.grant2.full_name))

        # Request with topics-paymentstate property
        response = self.client.post(reverse('export'), {
            'type': 'topic',
            'topics-tickets-larger': '',
            'topics-tickets-smaller': '',
            'topics-paymentstate': '',
            'topics-paymentstate-larger': '',
            'topics-paymentstate-smaller': ''
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 2)
        self.assertEqual(csvContent[1][0], str(self.topic1.name))
        self.assertEqual(csvContent[2][0], str(self.topic2.name))

    def test_export_users(self):
        # Request from unauthorized user
        response = self.client.post(reverse('export'), {
            'type': 'user',
            'users-created-larger': '',
            'users-created-smaller': '',
            'users-accepted-larger': '',
            'users-accepted-smaller': '',
            'users-paid-larger': ''
        })
        self.assertEqual(403, response.status_code)

        self.client.login(username=self.standardUser.username, password=self.password)

        # Request from authorized user without enabled is_staff property
        response = self.client.post(reverse('export'), {
            'type': 'user',
            'users-created-larger': '',
            'users-created-smaller': '',
            'users-accepted-larger': '',
            'users-accepted-smaller': '',
            'users-paid-larger': ''
        })
        self.assertEqual(403, response.status_code)

        self.client.logout()
        self.client.login(username=self.staffUser.username, password=self.password)

        # Request without user-permision property
        # In this case, the system will return all users from the database
        response = self.client.post(reverse('export'), {
            'type': 'user',
            'users-created-larger': '',
            'users-created-smaller': '',
            'users-accepted-larger': '',
            'users-accepted-smaller': '',
            'users-paid-larger': ''
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 3)

        userIDs = {int(u[0]) for u in csvContent[1:]}
        wantedUserIDs = {self.standardUser.id, self.staffUser.id, self.superuser.id}
        self.assertEqual(userIDs, wantedUserIDs)

        # Request with valid user-permision property
        response = self.client.post(reverse('export'), {
            'type': 'user',
            'users-created-larger': '',
            'users-created-smaller': '',
            'users-accepted-larger': '',
            'users-accepted-smaller': '',
            'users-paid-larger': '',
            'user-permision': 'normal'
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 1)
        self.assertEqual(csvContent[1][0], str(self.standardUser.id))

        response = self.client.post(reverse('export'), {
            'type': 'user',
            'users-created-larger': '',
            'users-created-smaller': '',
            'users-accepted-larger': '',
            'users-accepted-smaller': '',
            'users-paid-larger': '',
            'user-permision': 'staff'
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 2)

        userIDs = {int(u[0]) for u in csvContent[1:]}
        wantedUserIDs = {self.staffUser.id, self.superuser.id}
        self.assertEqual(userIDs, wantedUserIDs)

        response = self.client.post(reverse('export'), {
            'type': 'user',
            'users-created-larger': '',
            'users-created-smaller': '',
            'users-accepted-larger': '',
            'users-accepted-smaller': '',
            'users-paid-larger': '',
            'user-permision': 'superuser'
        })
        csvContent = self.read_csv(response.content)
        self.assertEqual(200, response.status_code)
        self.assertEqual(len(csvContent) - 1, 1)
        self.assertEqual(csvContent[1][0], str(self.superuser.id))

        # Request with invalid user-permision property
        response = self.client.post(reverse('export'), {
            'type': 'user',
            'users-created-larger': '',
            'users-created-smaller': '',
            'users-accepted-larger': '',
            'users-accepted-smaller': '',
            'users-paid-larger': '',
            'user-permision': 'invalid_user_permission'
        })
        self.assertEqual(400, response.status_code)

    def test_invalid_export_type(self):
        response = self.client.post(reverse('export'), {
            'type': 'invalid_export_type'
        })
        self.assertEqual(400, response.status_code)


class DocumentAccessTests(TestCase):
    def setUp(self):
        self.owner = {'user': User.objects.create(username='ticket_owner'), 'password': 'pw1'}
        self.other_user = {'user': User.objects.create(username='other_user'), 'password': 'pwo'}
        for u in (self.owner, self.other_user):
            u['user'].set_password(u['password'])
            u['user'].save()

        self.topic = Topic.objects.create(name='test_topic', ticket_expenses=True, grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        self.ticket = Ticket.objects.create(name='ticket', topic=self.topic, requested_user=self.owner['user'])

        self.doc = {'name': 'test.txt', 'content_type': 'text/plain', 'payload': 'hello, world!'}
        document = Document(ticket=self.ticket, filename=self.doc['name'], size=len(self.doc['payload']), content_type=self.doc['content_type'])
        document.payload.save(self.doc['name'], ContentFile(self.doc['payload']))

    def check_user_access(self, user, can_see, can_edit):
        c = Client()
        if user is not None:
            c.login(username=user['user'].username, password=user['password'])
            deny_code = 403
        else:
            deny_code = 302

        response = c.get(reverse('ticket_detail', kwargs={'pk': self.ticket.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['user_can_see_all_documents'], can_see)
        self.assertEqual(response.context['user_can_edit_documents'], can_edit)

        response = c.get(reverse('edit_ticket_docs', kwargs={'pk': self.ticket.id}))
        self.assertEqual(response.status_code, {True: 200, False: deny_code}[can_edit])

        response = c.get(reverse('upload_ticket_doc', kwargs={'pk': self.ticket.id}))
        self.assertEqual(response.status_code, {True: 200, False: deny_code}[can_edit])

        response = c.get(reverse('download_document', kwargs={'ticket_id': self.ticket.id, 'filename': self.doc['name']}))
        if can_see:
            self.assertEqual(response.status_code, 200)
            file_bytes = b''.join(response.streaming_content)
            self.assertEqual(file_bytes.decode('utf-8'), self.doc['payload'])
        else:
            self.assertEqual(response.status_code, deny_code)

    def test_anonymous_user_access(self):
        self.check_user_access(user=None, can_see=False, can_edit=False)

    def test_unrelated_user_access(self):
        self.check_user_access(user=self.other_user, can_see=False, can_edit=True)

    def test_ticket_owner_access(self):
        self.check_user_access(user=self.owner, can_see=True, can_edit=True)

    def test_auditor_access(self):
        topic_content = ContentType.objects.get(app_label='tracker', model='Document')
        ou = self.other_user['user']
        ou.user_permissions.add(Permission.objects.get(content_type=topic_content, codename='see_all_docs'))
        ou.save()
        self.check_user_access(user=self.other_user, can_see=True, can_edit=True)

    def test_supervisor_access(self):
        topic_content = ContentType.objects.get(app_label='tracker', model='Document')
        ou = self.other_user['user']
        ou.user_permissions.add(Permission.objects.get(content_type=topic_content, codename='edit_all_docs'))
        ou.save()
        self.check_user_access(user=self.other_user, can_see=True, can_edit=True)


class CacheTicketsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create(username='ticket_owner')
        self.topic = Topic.objects.create(name='test_topic', ticket_expenses=True, grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        self.ticket = Ticket.objects.create(name='ticket', topic=self.topic, requested_user=self.owner)

        # Run cache_tickets, to have script already run in tests; record if it fails
        call_command('cachetickets', *[], **{'base_path': '/tmp'})

    def test_cachetickets_is_json(self):
        for langcode, language in settings.LANGUAGES:
            json.loads(open('/tmp/%s.json' % langcode).read())
        is_json = True
        try:
            for langcode, language in settings.LANGUAGES:
                json.loads(open('/tmp/%s.json' % langcode).read())
        except Exception:
            is_json = False
        self.assertTrue(is_json)


class AdminTests(TestCase):
    def setUp(self):
        self.password = 'bar'
        self.user = User.objects.create_superuser(username='admin',
                                                  password=self.password,
                                                  email='test@test')

    def get_client(self):
        c = Client()
        c.login(username=self.user.username, password=self.password)
        return c

    def test_admin_ticket_not_found(self):
        # Generate and make sure the Ticket with the selected id doesn't exist
        while True:
            random_id = random.randint(1, 999999)
            if len(Ticket.objects.filter(id=random_id)) == 0:
                break

        c = self.get_client()
        response = c.get('/admin/tracker/ticket/%d/change/' % random_id)
        self.assertEqual(404, response.status_code)


class PreferencesTests(TestCase):
    def setUp(self):
        self.password = 'bar'
        self.user = User.objects.create_user(username='test', password=self.password)

    def get_client(self):
        c = Client()
        c.login(username=self.user.username, password=self.password)
        return c

    def test_details_load(self):
        c = self.get_client()
        r = c.get(reverse('user_details_change'))
        self.assertEqual(r.status_code, 200)

    def test_details_submit(self):
        c = self.get_client()
        r = c.post(reverse('user_details_change'), {
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'bank_account': '63770002/5500',
            'other_contact': 'foo',
            'other_identification': 'bar'
        })
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(id=self.user.id)
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.first_name, 'Test')
        self.assertEqual(user.last_name, 'User')
        self.assertEqual(user.trackerprofile.bank_account, '63770002/5500')
        self.assertEqual(user.trackerprofile.other_contact, 'foo')
        self.assertEqual(user.trackerprofile.other_identification, 'bar')

    def test_preferences_load(self):
        c = self.get_client()
        r = c.get(reverse('preferences'))
        self.assertEqual(r.status_code, 200)

    def test_preferences_submit(self):
        c = self.get_client()
        r = c.post(reverse("preferences"), {
            "document": "",
            "media_new": "",
            "comment": "",
            "user_content": "",
            "close": "",
            "display_items": "20",
            "email_language": "es"
        }, follow=True)

        self.assertEqual(r.status_code, 200)

        for notification in r.context["notification_types"]:
            if notification[0] in ("document", "media_new", "comment"):
                self.assertEqual(notification[2], True)
            else:
                self.assertEqual(notification[2], False)

        for ack_type in r.context["ack_types"]:
            if ack_type[0] in ("user_content", "close"):
                self.assertEqual(ack_type[2], True)
            else:
                self.assertEqual(ack_type[2], False)

        preferences = TrackerPreferences.objects.get(user=self.user)

        self.assertTrue("document" in preferences.muted_notifications)
        self.assertTrue("media_new" in preferences.muted_notifications)
        self.assertTrue("comment" in preferences.muted_notifications)
        self.assertTrue("user_content" in preferences.muted_ack)
        self.assertTrue("close" in preferences.muted_ack)
        self.assertEqual(preferences.display_items, 20)
        self.assertEqual(preferences.email_language, "es")
