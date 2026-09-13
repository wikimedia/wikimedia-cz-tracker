# -*- coding: utf-8 -*-

import base64
import csv
import datetime
import io
import json
import random
from decimal import Decimal
from unittest.mock import patch, Mock

import requests

from django.conf import settings
from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.forms.formsets import DELETION_FIELD_NAME
from django.forms.models import inlineformset_factory
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.client import Client
from django.urls import reverse
from django.utils import timezone

from background_task.models import Task
from social_django.models import UserSocialAuth

from socialauth.api import MediaWiki, MediaWikiError

from tracker.admin import ExpeditureInlineFormSet
from tracker.fio import FioPaymentManager
from tracker.mediainfo import MediaInfoSync
from tracker.services import PaymentService
from tracker.models import Ticket, Topic, Subtopic, Grant, MediaInfo, Expediture, Preexpediture, TrackerProfile, \
    Document, TrackerPreferences, BankAccount, Template, PaymentInfo, PaymentType, ExpenditureState, ImportInfo
from users.models import UserWrapper
from tracker.validators import validate_full_bank_account


class SimpleTicketTest(TestCase):
    def setUp(self):
        self.topic = Topic(name='topic1', grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        self.topic.save()

        self.ticket1 = Ticket(name='foo', requested_text='req1', topic=self.topic, description='foo foo')
        self.ticket1.save()

        self.ticket2 = Ticket(name='bar', requested_text='req2', topic=self.topic, description='bar bar')
        self.ticket2.save()

    def test_ticket_timestamps(self):
        self.assertTrue(self.ticket2.created >= self.ticket1.created)  # check ticket 2 is newer

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
        full_ticket.mediainfo_set.create(page_title='testSummary.jpg')
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
        self.open_topic = Topic(name='test_topic', open_for_tickets=True, ticket_media=True, grant=self.get_grant())
        self.open_topic.save()

        self.statutory_declaration_topic = Topic(name='statutory_topic', open_for_tickets=True, ticket_media=True, ticket_statutory_declaration=True, grant=self.get_grant())
        self.statutory_declaration_topic.save()

        self.subtopic = Subtopic(name='Test', topic=self.open_topic)
        self.subtopic2 = Subtopic(name='Test2', topic=self.statutory_declaration_topic)
        self.subtopic.save()
        self.subtopic2.save()

        self.password = 'password'
        self.user = User(username='user')
        self.user.set_password(self.password)
        self.user.save()

    def get_grant(self):
        q = Grant.objects.filter(slug='g')
        if len(q) == 0:
            return Grant.objects.create(full_name='g', short_name='g', slug='g')
        return q.all()[0]

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
        closed_topic = Topic(name='closed topic', open_for_tickets=False, grant=self.get_grant())
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

    def test_too_big_deposit3(self):
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
            'preexpediture-0-amount': '-1000',
        })
        self.assertEqual(200, response.status_code)
        self.assertFormError(response, 'ticketform', 'deposit', 'Your deposit is bigger than your preexpeditures')

    def test_correct_deposit2(self):
        c = self.get_client()
        response = c.post(reverse('create_ticket'), {
            'name': 'ticket',
            'topic': self.open_topic.id,
            'description': 'some desc',
            'deposit': '0',
            'expediture-INITIAL_FORMS': '0',
            'expediture-TOTAL_FORMS': '0',
            'preexpediture-INITIAL_FORMS': '0',
            'preexpediture-TOTAL_FORMS': '1',
            'preexpediture-0-description': 'foo',
            'preexpediture-0-amount': '-1000',
        })
        self.assertEqual(302, response.status_code)
        self.assertEqual(1, Ticket.objects.count())
        ticket = Ticket.objects.order_by('-created')[0]
        self.assertEqual(Decimal('0'), ticket.deposit)

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
        self.topic = Topic(name='topic', grant=self.get_grant())
        self.topic.save()

        self.statutory_topic = Topic(name='statutory_topic', ticket_statutory_declaration=True, grant=self.get_grant())
        self.statutory_topic.save()

        self.subtopic = Subtopic(name='subtopic', topic=self.topic)
        self.subtopic2 = Subtopic(name='subtopic2', topic=self.statutory_topic)
        self.subtopic.save()
        self.subtopic2.save()

        self.password = 'my_password'
        self.user = User(username='my_user')
        self.user.set_password(self.password)
        self.user.save()

    def get_grant(self):
        q = Grant.objects.filter(slug='g')
        if len(q) == 0:
            return Grant.objects.create(full_name='g', short_name='g', slug='g')
        return q.all()[0]

    def test_correct_choices(self):
        grant = self.get_grant()
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
            'expediture-0-payment_type': 'bank_transfer',
            'expediture-1-description': 'hundred',
            'expediture-1-amount': '100',
            'expediture-1-payment_type': 'bank_transfer',
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
            'expediture-0-payment_type': 'cash',
            'expediture-0-DELETE': 'on',
            'expediture-1-id': expeditures[1].id,
            'expediture-1-description': 'hundred+1',
            'expediture-1-amount': '101',
            'expediture-1-payment_type': 'card',
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
        self.grant = self.get_grant()
        self.topic = Topic.objects.create(name='t', grant=self.grant)
        self.password = 'my_password'
        self.user = User(username='my_user')
        self.user.set_password(self.password)
        self.user.save()
        self.ticket = Ticket.objects.create(name='ticket', topic=self.topic, requested_user=self.user)

    def get_grant(self):
        q = Grant.objects.filter(slug='g')
        if len(q) == 0:
            return Grant.objects.create(full_name='g', short_name='g', slug='g')
        return q.all()[0]

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
        self.topic = Topic(name='topic', grant=self.get_grant())
        self.topic.save()

        self.password = 'my_password'
        self.user = User(username='my_user')
        self.user.set_password(self.password)
        self.user.save()

        self.ticket = Ticket(name='ticket', topic=self.topic, requested_user=None, requested_text='foo')
        self.ticket.save()

    def get_grant(self):
        q = Grant.objects.filter(slug='g')
        if len(q) == 0:
            return Grant.objects.create(full_name='g', short_name='g', slug='g')
        return q.all()[0]

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
        topic_content = ContentType.objects.get(app_label='tracker', model='topic')
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

        self.topic = Topic(name='test_topic', ticket_expenses=True, grant=self.get_grant())
        self.topic.save()

        self.ticket = Ticket(name='foo', requested_user=self.user, topic=self.topic, rating_percentage=50)
        self.ticket.save()
        self.ticket.add_acks('content', 'docs', 'archive')
        self.ticket.expediture_set.create(description='foo', amount=200)
        self.ticket.expediture_set.create(description='foo', amount=100)
        self.ticket.mediainfoold_set.create(description='foo', count=5)
        self.ticket.mediainfo_set.create(page_title='test_summaryTest.jpg')
        self.ticket.mediainfo_set.create(page_title='test2_summary.jpg')

        self.ticket2 = Ticket(name='foo', requested_user=self.user, topic=self.topic, rating_percentage=100)
        self.ticket2.save()
        self.ticket2.add_acks('content', 'docs', 'archive')
        self.ticket2.expediture_set.create(description='foo', amount=600)
        self.ticket2.expediture_set.create(description='foo', amount=10)
        self.ticket2.mediainfoold_set.create(description='foo', count=5)
        self.ticket2.mediainfoold_set.create(description='foo', count=3)
        self.ticket2.mediainfo_set.create(page_title='test_summaryTest.jpg')

    def get_grant(self):
        q = Grant.objects.filter(slug='g')
        if len(q) == 0:
            return Grant.objects.create(full_name='g', short_name='g', slug='g')
        return q.all()[0]

    def test_topic_ticket_counts(self):
        self.assertEqual({'unpaid': 2}, self.topic.tickets_per_payment_status())
        for e in self.ticket.expediture_set.all():
            e.mark_paid()
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

        self.grant1 = Grant.objects.create(full_name='g1full', short_name='g1short', slug='g1slug')
        self.grant2 = Grant.objects.create(full_name='g2full', short_name='g2short', slug='g2slug')

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
        topic_content = ContentType.objects.get(app_label='tracker', model='document')
        ou = self.other_user['user']
        ou.user_permissions.add(Permission.objects.get(content_type=topic_content, codename='see_all_docs'))
        ou.save()
        self.check_user_access(user=self.other_user, can_see=True, can_edit=True)

    def test_supervisor_access(self):
        topic_content = ContentType.objects.get(app_label='tracker', model='document')
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

    def test_ticket_change_page_carries_the_javascript_hooks(self):
        """
        expediture.js is a static file, thus Django does not render it. It must
        not hold a template tag, it must find the payment fieldset by a class,
        and it must write the total into the element that the template has
        already translated.
        """
        grant = Grant.objects.create(full_name='g', short_name='g', slug='g')
        topic = Topic.objects.create(name='topic', grant=grant)
        ticket = Ticket.objects.create(name='T1', topic=topic)

        c = self.get_client()
        response = c.get('/admin/tracker/ticket/%d/change/' % ticket.id)
        self.assertEqual(200, response.status_code)

        html = response.content.decode('utf-8')
        self.assertIn('payment-details', html)
        self.assertRegex(html, r'<p class="total">\s*[^<]*<b>')

        js_path = finders.find('admin/tracker/ticket/expediture.js')
        self.assertIsNotNone(js_path)
        with open(js_path, encoding='utf-8') as fd:
            self.assertNotIn('{%', fd.read())


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
            'other_contact': 'foo',
            'other_identification': 'bar'
        })
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(id=self.user.id)
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.first_name, 'Test')
        self.assertEqual(user.last_name, 'User')
        self.assertEqual(user.trackerprofile.other_contact, 'foo')
        self.assertEqual(user.trackerprofile.other_identification, 'bar')

    def test_details_submit_keeps_deprecated_bank_account(self):
        profile = self.user.trackerprofile
        profile.bank_account = '63770002/5500'
        profile.save()

        c = self.get_client()
        r = c.post(reverse('user_details_change'), {
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'bank_account': '2101865133/2010',
            'other_contact': 'foo',
            'other_identification': 'bar'
        })
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(id=self.user.id)
        self.assertEqual(user.trackerprofile.bank_account, '63770002/5500')

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


class FakeCommons:
    """
    A fake of the MediaWiki API of Wikimedia Commons, for MediaWiki.request.

    It has the limits of the real API: 50 pages in each request, and a limit
    on the categories and the usages in each response.
    """

    def __init__(self, list_limit=500):
        self.files = {}
        self.contents = {}
        self.list_limit = list_limit
        self.calls = []
        self.edits = []
        self.fail_page_ids = set()

    def add_file(self, page_id, title, categories=(), usages=(), content=None, width=4000, height=3000):
        self.files[page_id] = {
            'title': title,
            'width': width,
            'height': height,
            'categories': list(categories),
            'usages': list(usages),
        }
        if content is not None:
            self.contents[page_id] = content

    def request(self, payload, method="POST", authorized_only=False, retries=0):
        payload = dict(payload)
        self.calls.append(payload)
        if payload.get('action') == 'edit':
            self.edits.append((payload['pageid'], payload['text'], payload['minor']))
            self.contents[payload['pageid']] = payload['text']
            return self._response({'edit': {'result': 'Success'}})
        if payload.get('meta') == 'tokens':
            return self._response({'query': {'tokens': {'csrftoken': '+\\'}}})
        if 'titles' in payload:
            return self._response(self._query_titles(payload))
        raw_page_ids = payload['pageids']
        if isinstance(raw_page_ids, list):
            raw_page_ids = '|'.join(str(page_id) for page_id in raw_page_ids)
        page_ids = [int(page_id) for page_id in str(raw_page_ids).split('|')]
        if len(page_ids) > 50:
            return self._response({'error': {'code': 'toomanyvalues'}})
        if self.fail_page_ids.intersection(page_ids):
            raise requests.exceptions.ConnectionError('fake connection error')
        if payload.get('prop') == 'revisions':
            return self._response(self._query_revisions(payload, page_ids))
        return self._response(self._query_files(payload, page_ids))

    @staticmethod
    def _response(data):
        response = Mock()
        response.json.return_value = data
        return response

    def _query_titles(self, payload):
        titles = payload['titles'].split('|') if isinstance(payload['titles'], str) else [payload['titles']]
        normalized = []
        pages = []
        by_title = {f['title']: page_id for page_id, f in self.files.items()}
        for title in titles:
            target = title.replace('_', ' ')
            if target != title:
                normalized.append({'from': title, 'to': target})
            if target in by_title:
                pages.append({'pageid': by_title[target], 'ns': 6, 'title': target})
            else:
                pages.append({'ns': 6, 'title': target, 'missing': True})
        if payload.get('formatversion') != 2:
            return {'query': {'pages': {
                str(page.get('pageid', -1)): {'title': page['title']} for page in pages
            }}}
        return {'query': {'normalized': normalized, 'pages': pages}}

    def _query_revisions(self, payload, page_ids):
        pages = []
        for page_id in page_ids:
            if page_id not in self.contents:
                pages.append({'pageid': page_id, 'missing': True})
                continue
            pages.append({'pageid': page_id, 'ns': 6, 'title': 'File:%d' % page_id, 'revisions': [
                {'slots': {'main': {'content': self.contents[page_id]}}}
            ]})
        if payload.get('formatversion') != 2:
            return {'query': {'pages': {
                str(page['pageid']): {'revisions': [{'slots': {'main': {'*': page['revisions'][0]['slots']['main']['content']}}}]}
                for page in pages if 'revisions' in page
            }}}
        return {'query': {'pages': pages}}

    def _query_files(self, payload, page_ids):
        props = payload['prop'].split('|')
        pages = {}
        for page_id in page_ids:
            if page_id not in self.files:
                pages[page_id] = {'pageid': page_id, 'missing': True}
                continue
            pages[page_id] = {'pageid': page_id, 'ns': 6, 'title': self.files[page_id]['title']}
            if 'imageinfo' in props:
                f = self.files[page_id]
                imageinfo = {
                    'canonicaltitle': f['title'],
                    'width': f['width'],
                    'height': f['height'],
                    'url': 'https://upload.example/%d.jpg' % page_id,
                }
                if payload.get('iiurlwidth'):
                    imageinfo['thumburl'] = 'https://upload.example/%dpx-%d.jpg' % (payload['iiurlwidth'], page_id)
                pages[page_id]['imageinfo'] = [imageinfo]

        result = {'query': {'pages': list(pages.values())}}
        continuation = {}
        if 'imageinfo' in props and len(page_ids) == 1:
            # The real API continues to the old versions of a single file
            continuation['iistart'] = '2006-03-07T15:51:32Z'
        for prop, key, field, make_item in (
                ('categories', 'clcontinue', 'categories', self._category),
                ('globalusage', 'gucontinue', 'usages', self._usage),
        ):
            if prop not in props:
                continue
            start_page_id, start_index = [int(x) for x in payload[key].split('|')] if key in payload else (0, 0)
            left = self.list_limit
            for page_id in sorted(page_ids):
                if page_id < start_page_id or page_id not in self.files:
                    continue
                items = self.files[page_id][field]
                index = start_index if page_id == start_page_id else 0
                while index < len(items) and left > 0:
                    pages[page_id].setdefault(prop, []).append(make_item(items[index]))
                    index += 1
                    left -= 1
                if index < len(items):
                    continuation[key] = '%d|%d' % (page_id, index)
                    break
        if continuation:
            continuation['continue'] = '||'
            result['continue'] = continuation
        return result

    @staticmethod
    def _category(category):
        title, hidden = category if isinstance(category, tuple) else (category, False)
        # With formatversion=2, the API gives the hidden flag for all the categories
        return {'ns': 14, 'title': title, 'hidden': hidden}

    @staticmethod
    def _usage(title):
        return {'title': title, 'wiki': 'cs.wikipedia.org', 'url': 'https://cs.wikipedia.org/wiki/%s' % title}

    def file_requests(self):
        return [call for call in self.calls if 'imageinfo' in call.get('prop', '')]


def make_response(status_code, headers=None, data=None):
    response = requests.Response()
    response.status_code = status_code
    response.reason = 'fake'
    response.url = 'https://commons.wikimedia.org/w/api.php'
    response.headers.update(headers or {})
    response._content = json.dumps(data or {}).encode('utf-8')
    response.request = Mock(headers={})
    return response


class MediaWikiClientTests(SimpleTestCase):
    def setUp(self):
        self.mw = MediaWiki(user=None, api_url='https://commons.wikimedia.org/w/api.php')

    @patch('socialauth.api.time.sleep')
    @patch('requests.Session.post')
    def test_request_sets_timeout(self, post, sleep):
        post.return_value = make_response(200)
        self.mw.request({'action': 'query'})
        self.assertEqual(post.call_args[1]['timeout'], MediaWiki.TIMEOUT)
        sleep.assert_not_called()

    @patch('socialauth.api.time.sleep')
    @patch('requests.Session.post')
    def test_request_does_not_retry_by_default(self, post, sleep):
        post.return_value = make_response(503)
        with self.assertRaises(requests.exceptions.HTTPError):
            self.mw.request({'action': 'query'})
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    @patch('socialauth.api.time.sleep')
    @patch('requests.Session.post')
    def test_request_retries_with_retry_after(self, post, sleep):
        post.side_effect = [make_response(429, {'Retry-After': '7'}), make_response(200, data={'ok': True})]
        response = self.mw.request({'action': 'query'}, retries=3)
        self.assertEqual(response.json(), {'ok': True})
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(7)

    @patch('socialauth.api.time.sleep')
    @patch('requests.Session.post')
    def test_request_limits_retry_wait(self, post, sleep):
        post.side_effect = [make_response(503, {'Retry-After': '100000'}), make_response(200)]
        self.mw.request({'action': 'query'}, retries=1)
        sleep.assert_called_once_with(MediaWiki.MAX_RETRY_WAIT)

    @patch('socialauth.api.time.sleep')
    @patch('requests.Session.post')
    def test_request_raises_after_last_retry(self, post, sleep):
        post.side_effect = requests.exceptions.ConnectionError('down')
        with self.assertRaises(requests.exceptions.ConnectionError):
            self.mw.request({'action': 'query'}, retries=2)
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch('socialauth.api.time.sleep')
    @patch('requests.Session.post')
    def test_request_does_not_retry_client_errors(self, post, sleep):
        post.return_value = make_response(400)
        with self.assertRaises(requests.exceptions.HTTPError):
            self.mw.request({'action': 'query'}, retries=3)
        self.assertEqual(post.call_count, 1)

    def test_get_contents_follows_continuation(self):
        responses = [
            {'continue': {'rvcontinue': '2|x', 'continue': '||'}, 'query': {'pages': [
                {'pageid': 1, 'revisions': [{'slots': {'main': {'content': 'one'}}}]},
                {'pageid': 2},
                {'pageid': 3, 'missing': True},
            ]}},
            {'query': {'pages': [
                {'pageid': 1},
                {'pageid': 2, 'revisions': [{'slots': {'main': {'content': 'two'}}}]},
                {'pageid': 3, 'missing': True},
            ]}},
        ]
        with patch.object(MediaWiki, 'request', side_effect=[Mock(json=Mock(return_value=r)) for r in responses]) as request:
            contents = self.mw.get_contents([1, 2, 3], retries=2)
        self.assertEqual(contents, {1: 'one', 2: 'two'})
        self.assertEqual(request.call_args_list[0][0][0]['pageids'], '1|2|3')
        self.assertEqual(request.call_args_list[1][0][0]['rvcontinue'], '2|x')
        self.assertEqual(request.call_args_list[1][1]['retries'], 2)

    def test_get_contents_raises_api_error(self):
        response = Mock(json=Mock(return_value={'error': {'code': 'toomanyvalues'}}))
        with patch.object(MediaWiki, 'request', return_value=response):
            with self.assertRaises(MediaWikiError):
                self.mw.get_contents([1])


class MediaInfoTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create(username='ticket_owner')
        self.topic = Topic.objects.create(name='test_topic', ticket_expenses=True,
                                          grant=Grant.objects.create(full_name='g', short_name='g', slug='g'))
        self.ticket = Ticket.objects.create(name='ticket', topic=self.topic, requested_user=self.owner)
        self.commons = FakeCommons()
        patcher = patch.object(MediaWiki, 'request', self.commons.request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def create_media(self, page_id, title=None, ticket=None):
        media = MediaInfo.objects.create(ticket=ticket or self.ticket, page_id=page_id, page_title=title)
        Task.objects.all().delete()
        return media

    def tasks(self, name):
        return Task.objects.filter(task_name='tracker.models.%s' % name)


class MediaInfoRefreshTests(MediaInfoTestCase):
    def test_refresh_sends_batches_of_50(self):
        for page_id in range(1, 121):
            self.commons.add_file(page_id, 'File:%d.jpg' % page_id)
            self.create_media(page_id, 'File:%d.jpg' % page_id)

        Ticket.update_media.task_function(self.ticket.id)

        requests_sent = self.commons.file_requests()
        self.assertEqual(len(requests_sent), 3)
        self.assertTrue(all(len(call['pageids'].split('|')) <= 50 for call in requests_sent))
        media = MediaInfo.objects.get(page_id=77)
        self.assertEqual(media.page_title, 'File:77.jpg')
        self.assertEqual(media.thumb_url, 'https://upload.example/200px-77.jpg')
        self.assertEqual((media.width, media.height), (4000, 3000))

    def test_refresh_stores_all_categories_and_usages(self):
        self.commons.list_limit = 2
        categories = ['Category:A', ('Category:Hidden', True), 'Category:B', 'Category:C', 'Category:D']
        usages = ['U1', 'U2', 'U3', 'U4', 'U5']
        self.commons.add_file(1, 'File:1.jpg', categories=categories, usages=usages)
        self.commons.add_file(2, 'File:2.jpg', categories=['Category:E'], usages=['U6'])
        media = self.create_media(1, 'File:1.jpg')
        self.create_media(2, 'File:2.jpg')

        Ticket.update_media.task_function(self.ticket.id)

        self.assertEqual(sorted(media.mediainfocategory_set.values_list('title', flat=True)),
                         ['Category:A', 'Category:B', 'Category:C', 'Category:D'])
        self.assertEqual(sorted(media.mediainfousage_set.values_list('title', flat=True)), usages)
        self.assertEqual(list(MediaInfo.objects.get(page_id=2).mediainfousage_set.values_list('title', flat=True)),
                         ['U6'])
        self.assertTrue(len(self.commons.calls) > 1)

    def test_refresh_stores_visible_categories(self):
        self.commons.add_file(1, 'File:1.jpg', categories=['Category:Visible', ('Category:Hidden', True)])
        media = self.create_media(1, 'File:1.jpg')

        Ticket.update_media.task_function(self.ticket.id)

        self.assertEqual(list(media.mediainfocategory_set.values_list('title', flat=True)), ['Category:Visible'])

    def test_refresh_of_one_file_does_not_get_old_versions(self):
        self.commons.add_file(1, 'File:1.jpg', categories=['Category:A'])
        self.create_media(1, 'File:1.jpg')

        Ticket.update_media.task_function(self.ticket.id)

        self.assertEqual(len(self.commons.calls), 1)
        self.assertFalse(any('iistart' in call for call in self.commons.calls))

    def test_refresh_does_not_write_unchanged_data(self):
        self.commons.add_file(1, 'File:1.jpg', categories=['Category:A', 'Category:B'], usages=['U1'])
        media = self.create_media(1, 'File:1.jpg')
        Ticket.update_media.task_function(self.ticket.id)
        category_ids = set(media.mediainfocategory_set.values_list('id', flat=True))
        usage_ids = set(media.mediainfousage_set.values_list('id', flat=True))

        with patch.object(MediaInfo, 'save', autospec=True) as save:
            Ticket.update_media.task_function(self.ticket.id)
        save.assert_not_called()
        self.assertEqual(set(media.mediainfocategory_set.values_list('id', flat=True)), category_ids)
        self.assertEqual(set(media.mediainfousage_set.values_list('id', flat=True)), usage_ids)

    def test_refresh_writes_only_changed_rows(self):
        self.commons.add_file(1, 'File:1.jpg', categories=['Category:A', 'Category:B'], usages=['U1', 'U2'])
        media = self.create_media(1, 'File:1.jpg')
        Ticket.update_media.task_function(self.ticket.id)
        kept_category = media.mediainfocategory_set.get(title='Category:A')
        kept_usage = media.mediainfousage_set.get(title='U1')

        self.commons.files[1]['categories'] = ['Category:A', 'Category:C']
        self.commons.files[1]['usages'] = ['U1', 'U3']
        Ticket.update_media.task_function(self.ticket.id)

        self.assertEqual(sorted(media.mediainfocategory_set.values_list('title', flat=True)), ['Category:A', 'Category:C'])
        self.assertEqual(sorted(media.mediainfousage_set.values_list('title', flat=True)), ['U1', 'U3'])
        self.assertTrue(media.mediainfocategory_set.filter(id=kept_category.id).exists())
        self.assertTrue(media.mediainfousage_set.filter(id=kept_usage.id).exists())

    def test_refresh_stores_new_title_of_renamed_file(self):
        self.commons.add_file(1, 'File:New name.jpg')
        media = self.create_media(1, 'File:Old name.jpg')

        Ticket.update_media.task_function(self.ticket.id)

        media.refresh_from_db()
        self.assertEqual(media.page_title, 'File:New name.jpg')

    def test_refresh_finds_new_page_id_from_title(self):
        self.commons.add_file(200, 'File:Uploaded again.jpg', usages=['U1'])
        media = self.create_media(100, 'File:Uploaded again.jpg')

        Ticket.update_media.task_function(self.ticket.id)

        media.refresh_from_db()
        self.assertEqual(media.page_id, 200)
        self.assertEqual(media.thumb_url, 'https://upload.example/200px-200.jpg')
        self.assertEqual(list(media.mediainfousage_set.values_list('title', flat=True)), ['U1'])

    def test_refresh_finds_page_id_of_media_without_page_id(self):
        self.commons.add_file(5, 'File:No id.jpg')
        media = self.create_media(5, 'File:No id.jpg')
        MediaInfo.objects.filter(id=media.id).update(page_id=None)

        Ticket.update_media.task_function(self.ticket.id)

        media.refresh_from_db()
        self.assertEqual(media.page_id, 5)
        self.assertEqual(media.width, 4000)

    def test_refresh_deletes_media_of_missing_file(self):
        self.commons.add_file(1, 'File:Exists.jpg')
        self.create_media(1, 'File:Exists.jpg')
        self.create_media(2, 'File:Deleted.jpg')

        Ticket.update_media.task_function(self.ticket.id)

        self.assertEqual(list(MediaInfo.objects.values_list('page_title', flat=True)), ['File:Exists.jpg'])

    def test_refresh_keeps_media_without_page_id_and_title(self):
        media = self.create_media(3, 'File:x.jpg')
        MediaInfo.objects.filter(id=media.id).update(page_id=None, page_title=None)

        Ticket.update_media.task_function(self.ticket.id)

        self.assertTrue(MediaInfo.objects.filter(id=media.id).exists())

    def test_refresh_deletes_duplicate_media(self):
        self.commons.add_file(1, 'File:Same file.jpg')
        self.create_media(1, 'File:Same file.jpg')
        duplicate = self.create_media(9, 'File:Same_file.jpg')
        MediaInfo.objects.filter(id=duplicate.id).update(page_id=None)

        Ticket.update_media.task_function(self.ticket.id)

        self.assertEqual(list(MediaInfo.objects.values_list('page_title', flat=True)), ['File:Same file.jpg'])

    def test_failed_batch_does_not_stop_other_batches(self):
        for page_id in range(1, 61):
            self.commons.add_file(page_id, 'File:%d.jpg' % page_id)
            self.create_media(page_id, 'File:Old %d.jpg' % page_id)
        self.commons.fail_page_ids = {10}

        with self.assertRaises(MediaWikiError):
            Ticket.update_media.task_function(self.ticket.id)

        # The first batch failed. Its media do not change, and they are not deleted.
        self.assertEqual(MediaInfo.objects.count(), 60)
        self.assertEqual(MediaInfo.objects.get(page_id=10).page_title, 'File:Old 10.jpg')
        self.assertEqual(MediaInfo.objects.get(page_id=55).page_title, 'File:55.jpg')
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.media_updated)

    def test_update_media_does_not_save_ticket(self):
        self.commons.add_file(1, 'File:1.jpg')
        self.create_media(1, 'File:1.jpg')
        updated = Ticket.objects.get(id=self.ticket.id).updated
        refresh = MediaInfoSync.refresh

        def refresh_with_concurrent_edit(sync, medias):
            Ticket.objects.filter(id=self.ticket.id).update(name='edited during refresh')
            return refresh(sync, medias)

        with patch.object(MediaInfoSync, 'refresh', autospec=True, side_effect=refresh_with_concurrent_edit):
            Ticket.update_media.task_function(self.ticket.id)

        ticket = Ticket.objects.get(id=self.ticket.id)
        self.assertIsNotNone(ticket.media_updated)
        self.assertEqual(ticket.updated, updated)
        self.assertEqual(ticket.name, 'edited during refresh')

    def test_update_media_flushes_media_count(self):
        self.commons.add_file(1, 'File:1.jpg')
        self.create_media(1, 'File:1.jpg')
        self.create_media(2, 'File:Deleted.jpg')
        self.assertEqual(Ticket.objects.get(id=self.ticket.id).media_count(), 2)

        Ticket.update_media.task_function(self.ticket.id)

        self.assertEqual(Ticket.objects.get(id=self.ticket.id).media_count(), 1)

    def test_update_media_schedules_template_update(self):
        self.commons.add_file(1, 'File:1.jpg')
        self.create_media(1, 'File:1.jpg')

        with override_settings(TRACKER_MAINTENANCE_USER_ID=self.owner.id):
            Ticket.update_media.task_function(self.ticket.id)

        task = self.tasks('_update_mediainfo').get()
        self.assertEqual(json.loads(task.task_params), [[self.ticket.id, self.owner.id], {}])

    def test_queued_store_mediawiki_data_task_still_works(self):
        self.commons.add_file(1, 'File:Example.svg')
        media = self.create_media(1)

        MediaInfo.store_mediawiki_data.task_function(media.id)

        media.refresh_from_db()
        self.assertEqual(media.page_title, 'File:Example.svg')


class MediaInfoSchedulingTests(MediaInfoTestCase):
    def test_update_media_is_in_queue_once(self):
        Ticket.update_media(self.ticket.id)
        Ticket.update_media(self.ticket.id)
        Ticket.update_media(self.ticket.id + 1)

        self.assertEqual(self.tasks('update_media').filter(task_params='[[%d], {}]' % self.ticket.id).count(), 1)
        self.assertEqual(self.tasks('update_media').count(), 2)

    def test_new_media_schedule_one_refresh(self):
        for page_id in range(1, 4):
            MediaInfo.objects.create(ticket=self.ticket, page_id=page_id, page_title='File:%d.jpg' % page_id)

        self.assertEqual(self.tasks('update_media').count(), 1)
        self.assertEqual(self.tasks('store_mediawiki_data').count(), 0)

    def test_media_saved_during_refresh_schedules_new_refresh(self):
        Ticket.update_media(self.ticket.id)
        Task.objects.update(locked_by='1234', locked_at=timezone.now())

        MediaInfo.objects.create(ticket=self.ticket, page_id=1, page_title='File:1.jpg')

        self.assertEqual(self.tasks('update_media').count(), 2)

    @override_settings(TRACKER_MAINTENANCE_USER_ID=1)
    def test_ticket_save_does_not_update_templates(self):
        self.create_media(1, 'File:1.jpg')
        ticket = Ticket.objects.get(id=self.ticket.id)
        ticket.description = 'changed'
        ticket.save()
        ticket.update_payment_status()

        self.assertEqual(self.tasks('_update_mediainfo').count(), 0)

    def test_subtopic_change_updates_templates(self):
        self.create_media(1, 'File:1.jpg')
        subtopic = Subtopic.objects.create(name='subtopic', topic=self.topic)
        ticket = Ticket.objects.get(id=self.ticket.id)
        ticket.subtopic = subtopic

        with override_settings(TRACKER_MAINTENANCE_USER_ID=self.owner.id):
            ticket.save()

        task = self.tasks('_update_mediainfo').get()
        self.assertEqual(json.loads(task.task_params), [[self.ticket.id, self.owner.id], {}])

    def test_new_ticket_does_not_update_templates(self):
        subtopic = Subtopic.objects.create(name='subtopic', topic=self.topic)
        with override_settings(TRACKER_MAINTENANCE_USER_ID=self.owner.id):
            Ticket.objects.create(name='new', topic=self.topic, subtopic=subtopic)

        self.assertEqual(self.tasks('_update_mediainfo').count(), 0)


class MediaInfoTemplateTests(MediaInfoTestCase):
    def template(self, media):
        return '{{%s|podtéma=%s|rok=%d|tiket=%d}}' % (
            settings.MEDIAINFO_MEDIAWIKI_TEMPLATE, media.ticket.subtopic or '', media.created.year, media.ticket.id)

    def test_add_to_mediawiki(self):
        self.commons.contents[937952] = '{{Information|description=Example}}\n[[Category:Example]]'
        media = self.create_media(937952)

        MediaInfo.add_to_mediawiki.task_function(media.id, self.owner.id)

        page_id, text, minor = self.commons.edits[0]
        self.assertEqual(page_id, 937952)
        self.assertEqual(text, '{{Information|description=Example}}\n%s\n[[Category:Example]]' % self.template(media))
        self.assertFalse(minor)

    def test_remove_from_mediawiki(self):
        media = self.create_media(937952)
        self.commons.contents[937952] = '{{Information}}\n%s\n[[Category:Example]]' % self.template(media)

        MediaInfo.remove_from_mediawiki.task_function(media.page_id, self.owner.id)

        self.assertEqual(self.commons.edits, [(937952, '{{Information}}\n[[Category:Example]]', True)])

    def test_add_templates_reads_pages_in_batches(self):
        for page_id in range(1, 61):
            self.commons.contents[page_id] = '{{Information}}'
            self.create_media(page_id, 'File:%d.jpg' % page_id)

        Ticket._update_mediainfo.task_function(self.ticket.id, self.owner.id)

        reads = [call for call in self.commons.calls if call.get('prop') == 'revisions']
        self.assertEqual(len(reads), 2)
        self.assertTrue(all(len(call['pageids'].split('|')) <= 50 for call in reads))
        self.assertEqual(len(self.commons.edits), 60)

    def test_add_templates_edits_only_pages_that_change(self):
        subtopic = Subtopic.objects.create(name='new subtopic', topic=self.topic)
        Ticket.objects.filter(id=self.ticket.id).update(subtopic=subtopic)
        correct = self.create_media(1, 'File:1.jpg')
        outdated = self.create_media(2, 'File:2.jpg')
        without_information = self.create_media(3, 'File:3.jpg')
        self.create_media(4, 'File:Missing.jpg')
        self.commons.contents[1] = '{{Information}}\n' + self.template(MediaInfo.objects.get(id=correct.id))
        self.commons.contents[2] = '{{Information}}\n{{%s|podtéma=old|rok=2020|tiket=%d}}\n[[Category:A]]' % (
            settings.MEDIAINFO_MEDIAWIKI_TEMPLATE, self.ticket.id)
        self.commons.contents[3] = 'No information template'

        Ticket._update_mediainfo.task_function(self.ticket.id, self.owner.id)

        outdated = MediaInfo.objects.get(id=outdated.id)
        without_information = MediaInfo.objects.get(id=without_information.id)
        self.assertEqual(self.commons.edits, [
            (2, '{{Information}}\n' + self.template(outdated) + '\n[[Category:A]]', False),
            (3, 'No information template\n' + self.template(without_information), True),
        ])

    def test_failed_read_does_not_stop_other_batches(self):
        for page_id in range(1, 61):
            self.commons.contents[page_id] = '{{Information}}'
            self.create_media(page_id, 'File:%d.jpg' % page_id)
        self.commons.fail_page_ids = {1}

        with self.assertRaises(MediaWikiError):
            Ticket._update_mediainfo.task_function(self.ticket.id, self.owner.id)

        self.assertEqual(sorted(page_id for page_id, text, minor in self.commons.edits), list(range(51, 61)))

    def test_template_update_is_in_queue_once(self):
        Ticket._update_mediainfo(self.ticket.id, self.owner.id)
        Ticket._update_mediainfo(self.ticket.id, self.owner.id)

        self.assertEqual(self.tasks('_update_mediainfo').count(), 1)

    @override_settings(MEDIAINFO_MEDIAWIKI_TEMPLATE=None)
    def test_disabled_templates_do_not_change_pages(self):
        self.commons.contents[1] = '{{Information}}'
        media = self.create_media(1, 'File:1.jpg')

        Ticket._update_mediainfo.task_function(self.ticket.id, self.owner.id)
        MediaInfo.add_to_mediawiki.task_function(media.id, self.owner.id)
        MediaInfo.remove_from_mediawiki.task_function(media.page_id, self.owner.id)

        self.assertEqual(self.commons.calls, [])


class MediaInfoSyncTemplateTextTests(SimpleTestCase):
    template = '{{%s|podtéma=|rok=2026|tiket=1}}' % settings.MEDIAINFO_MEDIAWIKI_TEMPLATE

    def test_add_template_after_information_template(self):
        text = '{{Information|description={{cs|Popis}}}}\n[[Category:A]]'
        self.assertEqual(MediaInfoSync.add_template(text, self.template), (
            '{{Information|description={{cs|Popis}}}}\n%s\n[[Category:A]]' % self.template, False))

    def test_add_template_at_end_without_information_template(self):
        self.assertEqual(MediaInfoSync.add_template('Text', self.template), ('Text\n' + self.template, True))

    def test_add_template_replaces_old_template(self):
        text = '{{Information}}\n{{%s|podtéma=old|rok=2020|tiket=1}}\n[[Category:A]]' % settings.MEDIAINFO_MEDIAWIKI_TEMPLATE
        self.assertEqual(MediaInfoSync.add_template(text, self.template), (
            '{{Information}}\n%s\n[[Category:A]]' % self.template, False))

    def test_add_template_does_not_change_text_with_template(self):
        self.assertEqual(MediaInfoSync.add_template('{{Information}}\n' + self.template, self.template), (None, None))


class MediaImportTests(MediaInfoTestCase):
    def test_import_saves_each_ticket_once(self):
        User.objects.create_superuser(username='importer', password='pw', email='importer@example.com')
        other_ticket = Ticket.objects.create(name='other', topic=self.topic)
        for page_id in range(1, 4):
            self.commons.add_file(page_id, 'File:%d.jpg' % page_id)
        csvfile = io.BytesIO(b'ticket_id;name\n%d;File:1.jpg\n%d;File:2.jpg\n%d;File:3.jpg\n' % (
            self.ticket.id, self.ticket.id, other_ticket.id))
        csvfile.name = 'media.csv'
        client = Client()
        client.login(username='importer', password='pw')

        with patch.object(Ticket, 'save', autospec=True, side_effect=Ticket.save) as save:
            response = client.post(reverse('importcsv'), {'type': 'media', 'csvfile': csvfile})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(sorted(call[0][0].id for call in save.call_args_list), sorted([self.ticket.id, other_ticket.id]))
        self.assertEqual(sorted(self.ticket.mediainfo_set.values_list('page_title', flat=True)), ['File:1.jpg', 'File:2.jpg'])
        self.assertEqual(self.tasks('_update_mediainfo').count(), 0)

    def test_import_of_media_that_the_ticket_has(self):
        User.objects.create_superuser(username='importer', password='pw', email='importer@example.com')
        for page_id in range(1, 3):
            self.commons.add_file(page_id, 'File:%d.jpg' % page_id)
        self.create_media(1, 'File:1.jpg')
        csvfile = io.BytesIO(b'ticket_id;name\n%d;File:1.jpg\n%d;File:2.jpg\n%d;File:2.jpg\n' % (
            self.ticket.id, self.ticket.id, self.ticket.id))
        csvfile.name = 'media.csv'
        client = Client()
        client.login(username='importer', password='pw')

        response = client.post(reverse('importcsv'), {'type': 'media', 'csvfile': csvfile})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(sorted(self.ticket.mediainfo_set.values_list('page_title', flat=True)), ['File:1.jpg', 'File:2.jpg'])


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                                       'LOCATION': 'oauth-middleware-tests'}})
class InvalidOauthMiddlewareTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='oauth_user', password='pw')
        self.social = UserSocialAuth.objects.create(user=self.user, provider='mediawiki', uid='1', extra_data={
            'access_token': {'oauth_token': 'token-1', 'oauth_token_secret': 'secret'}
        })
        self.client.login(username='oauth_user', password='pw')

    def userinfo_response(self, data):
        return Mock(json=Mock(return_value=data))

    def test_valid_tokens_are_checked_once(self):
        with patch.object(MediaWiki, 'request', return_value=self.userinfo_response({'query': {'userinfo': {}}})) as request:
            self.client.get(reverse('ticket_list'))
            self.client.get(reverse('ticket_list'))
        self.assertEqual(request.call_count, 1)

    def test_new_tokens_are_checked_again(self):
        with patch.object(MediaWiki, 'request', return_value=self.userinfo_response({'query': {'userinfo': {}}})) as request:
            self.client.get(reverse('ticket_list'))
            self.social.extra_data = {'access_token': {'oauth_token': 'token-2', 'oauth_token_secret': 'secret'}}
            self.social.save()
            self.client.get(reverse('ticket_list'))
        self.assertEqual(request.call_count, 2)

    def test_invalid_tokens_redirect_every_time(self):
        invalid = self.userinfo_response({'error': {'code': 'mwoauth-invalid-authorization'}})
        with patch.object(MediaWiki, 'request', return_value=invalid) as request:
            first = self.client.get(reverse('ticket_list'))
            second = self.client.get(reverse('ticket_list'))
        expected = reverse('invalid_oauth_tokens', kwargs={'provider': 'mediawiki'})
        self.assertTrue(first['Location'].startswith(expected))
        self.assertTrue(second['Location'].startswith(expected))
        self.assertEqual(request.call_count, 2)


class AutomationPaymentTests(TestCase):
    def setUp(self):
        self.grant = Grant.objects.create(full_name='Auto Grant', short_name='AG', slug='ag')
        self.topic = Topic.objects.create(name='Auto Topic', grant=self.grant)
        self.password = 'bar'
        self.user = User.objects.create_user(username='test', password=self.password)

        self.profile = self.user.trackerprofile

        self.saved_acc = BankAccount.objects.create(
            user=self.profile,
            name='My account',
            number='2000145399',
            bank='0800'
        )

    def test_template_validation(self):
        # A) no bank account -> ValidationError
        t_empty = Template(template_name="blank template", amount=100)
        with self.assertRaises(ValidationError):
            t_empty.clean()

        # B) both saved account link and manual account -> ValidationError
        t_both = Template(
            template_name="wrong template",
            amount=100,
            saved_account=self.saved_acc,
            account_number="19-2000145399/0800"
        )
        with self.assertRaises(ValidationError):
            t_both.clean()

        # C) just saved account -> ok
        t_saved = Template(
            template_name="saved account template",
            amount=100,
            saved_account=self.saved_acc
        )
        try:
            t_saved.clean()
        except ValidationError:
            self.fail("Template.clean() throw an error")

        # D) just manual account -> ok
        t_manual = Template(
            template_name="manual account template",
            amount=100,
            account_number="19-2000145399/0800"
        )
        try:
            t_manual.clean()
        except ValidationError:
            self.fail("Template.clean() throw an error")

        # E) wrong manual account -> error
        t_wrong_manual = Template(
            template_name="wrong manual account template",
            amount=100,
            account_number="0123456789/0800"
        )
        with self.assertRaises(ValidationError):
            t_wrong_manual.full_clean()

    def test_bank_account_validator(self):
        # valid account
        try:
            validate_full_bank_account("19-2000145399/0800")
            validate_full_bank_account("2101865133/2010")
        except ValidationError:
            self.fail("Validátor nečekaně vyhodil platné číslo bankovního účtu.")

        # invalid formats -> ValidationError
        with self.assertRaises(ValidationError):
            validate_full_bank_account("abcd")

        with self.assertRaises(ValidationError):
            validate_full_bank_account("2101865133")  # missing bank code

        with self.assertRaises(ValidationError):
            validate_full_bank_account("2101865133/123")  # wrong bank code

        with self.assertRaises(ValidationError):
            validate_full_bank_account("2101865133/ABCD")  # wrong bank code

    def test_payment_info_target_account(self):
        # A) saved account
        info_saved = PaymentInfo.objects.create(saved_account=self.saved_acc)
        self.assertEqual(info_saved.get_target_account(), self.saved_acc.full_number)

        # B) manual account
        info_manual = PaymentInfo.objects.create(account_number="111222333/0100")
        self.assertEqual(info_manual.get_target_account(), "111222333/0100")

    def test_expenditure_computed_state(self):
        from tracker.models import Ticket
        ticket = Ticket.objects.create(name='Test ticket', topic=self.topic, requested_user=self.user)

        # cash expenditure
        exp = Expediture.objects.create(
            ticket=ticket,
            description='Test výdaj',
            amount=500,
            payment_type=PaymentType.CASH
        )

        self.assertEqual(exp.get_computed_state(), ExpenditureState.WAITING)

        # bank transfer without account
        exp.payment_type = PaymentType.BANK_TRANSFER
        exp.save()
        self.assertEqual(exp.get_computed_state(), ExpenditureState.MISSING)

        # with account
        exp.payment_info = PaymentInfo.objects.create(saved_account=self.saved_acc)

        # grant fix
        self.grant.source_bank_account = "19-123457/0710"
        self.grant.save()
        exp.save()

        self.assertEqual(exp.get_computed_state(), ExpenditureState.READY)

        # with import error
        exp.import_info = ImportInfo.objects.create(error=True)
        exp.save()

        self.assertEqual(exp.get_computed_state(), ExpenditureState.ERROR)

        # imported
        exp.import_info.error = False
        exp.import_info.imported_at = timezone.now()
        exp.import_info.due_date = timezone.now().date()
        exp.import_info.save()
        exp.save()

        self.assertEqual(exp.get_computed_state(), ExpenditureState.IMPORTED)

        # paid
        exp.mark_paid()

        self.assertEqual(exp.get_computed_state(), ExpenditureState.PAID)


class CofinancingServiceTests(TestCase):
    def setUp(self):
        self.grant = Grant.objects.create(full_name='g', short_name='g', slug='g')
        self.topic = Topic.objects.create(name='topic', grant=self.grant)
        self.ticket1 = Ticket.objects.create(name='T1', topic=self.topic)
        self.ticket2 = Ticket.objects.create(name='T2', topic=self.topic)
        self.expenditure = Expediture.objects.create(ticket=self.ticket1, description='Nakup techniky', amount=1000)

    def test_process_cofinancing_link_ticket(self):
        PaymentService.process_cofinancing_link(self.expenditure, self.ticket2, None, 500)
        self.expenditure.refresh_from_db()

        self.assertEqual(self.expenditure.amount, -500)

        linked = self.expenditure.linked_expenditure
        self.assertIsNotNone(linked)
        self.assertEqual(linked.ticket, self.ticket2)
        self.assertEqual(linked.amount, 500)
        self.assertEqual(linked.payment_type, PaymentType.INTERNAL_TRANSFER)

    def test_process_cofinancing_link_switch_to_account(self):
        PaymentService.process_cofinancing_link(self.expenditure, self.ticket2, None, 500)
        self.expenditure.refresh_from_db()
        transfer_id = self.expenditure.linked_expenditure_id
        self.assertIsNotNone(transfer_id)

        # switching the source from a ticket to a bare account must drop the transfer
        # without taking the income row with it.
        PaymentService.process_cofinancing_link(self.expenditure, None, '2000145399/2010', 500)

        self.expenditure.refresh_from_db()
        self.assertIsNone(self.expenditure.linked_expenditure)
        self.assertFalse(Expediture.objects.filter(id=transfer_id).exists())

    def test_mark_paid_syncs_cofinancing_pair(self):
        PaymentService.process_cofinancing_link(self.expenditure, self.ticket2, None, 500)
        self.expenditure.refresh_from_db()

        transfer = self.expenditure.linked_expenditure
        transfer.mark_paid()

        transfer.refresh_from_db()
        self.expenditure.refresh_from_db()
        self.assertTrue(transfer.paid)
        self.assertTrue(self.expenditure.paid)

        transfer.mark_paid(False)
        transfer.refresh_from_db()
        self.expenditure.refresh_from_db()
        self.assertFalse(transfer.paid)
        self.assertFalse(self.expenditure.paid)


class AdminExpeditureDeleteGuardTests(TestCase):
    """
    A co-financing pair is two rows that point at each other with a mutual
    CASCADE. A delete of one row therefore also removes the other row, which
    can be paid or can have an order at the bank. The admin formset must refuse
    to delete either row.
    """

    def setUp(self):
        self.grant = Grant.objects.create(full_name='g', short_name='g', slug='g')
        self.topic = Topic.objects.create(name='topic', grant=self.grant)
        self.ticket1 = Ticket.objects.create(name='T1', topic=self.topic)
        self.ticket2 = Ticket.objects.create(name='T2', topic=self.topic)

        self.income = Expediture.objects.create(
            ticket=self.ticket1, description='Nakup techniky', amount=1000,
            payment_type=PaymentType.INCOME,
        )
        PaymentService.process_cofinancing_link(self.income, self.ticket2, None, 500)
        self.income.refresh_from_db()
        self.transfer = self.income.linked_expenditure

    def _build_formset(self, ticket, expenditure):
        """Build a bound admin inline formset that asks to delete one row."""
        formset_class = inlineformset_factory(
            Ticket, Expediture, formset=ExpeditureInlineFormSet,
            fields=('description', 'amount'), extra=0, can_delete=True,
        )
        prefix = formset_class.get_default_prefix()
        data = {
            '%s-TOTAL_FORMS' % prefix: '1',
            '%s-INITIAL_FORMS' % prefix: '1',
            '%s-MIN_NUM_FORMS' % prefix: '0',
            '%s-MAX_NUM_FORMS' % prefix: '1000',
            '%s-0-id' % prefix: str(expenditure.pk),
            '%s-0-ticket' % prefix: str(ticket.pk),
            '%s-0-description' % prefix: expenditure.description,
            '%s-0-amount' % prefix: str(expenditure.amount),
            '%s-0-DELETE' % prefix: 'on',
        }
        return formset_class(data, instance=ticket, queryset=Expediture.objects.filter(pk=expenditure.pk))

    def _try_to_delete(self, ticket, expenditure):
        formset = self._build_formset(ticket, expenditure)
        if formset.is_valid():
            formset.save()

    def test_delete_is_disabled_for_both_halves(self):
        for ticket, expenditure in ((self.ticket1, self.income), (self.ticket2, self.transfer)):
            formset = self._build_formset(ticket, expenditure)
            self.assertTrue(formset.forms[0].fields[DELETION_FIELD_NAME].disabled)

    def test_deleting_the_income_row_keeps_the_pair(self):
        self._try_to_delete(self.ticket1, self.income)

        self.assertTrue(Expediture.objects.filter(pk=self.income.pk).exists())
        self.assertTrue(Expediture.objects.filter(pk=self.transfer.pk).exists())

    def test_deleting_the_transfer_row_keeps_the_pair(self):
        self._try_to_delete(self.ticket2, self.transfer)

        self.assertTrue(Expediture.objects.filter(pk=self.income.pk).exists())
        self.assertTrue(Expediture.objects.filter(pk=self.transfer.pk).exists())

    def test_imported_expenditure_cannot_be_deleted(self):
        expenditure = Expediture.objects.create(
            ticket=self.ticket1, description='Kancelarske potreby', amount=200,
            import_info=ImportInfo.objects.create(),
        )

        self._try_to_delete(self.ticket1, expenditure)

        self.assertTrue(Expediture.objects.filter(pk=expenditure.pk).exists())

    def test_plain_expenditure_can_still_be_deleted(self):
        expenditure = Expediture.objects.create(
            ticket=self.ticket1, description='Kancelarske potreby', amount=200,
        )

        self._try_to_delete(self.ticket1, expenditure)

        self.assertFalse(Expediture.objects.filter(pk=expenditure.pk).exists())


class FioMessageMatchingTests(SimpleTestCase):
    """
    Fio's message field can carry extra text around our payment reference, so
    the matcher does a substring search -- but it must be anchored, or
    "WMCZ ticket #1" silently matches ticket #12's transaction.
    """

    CASES = [
        # (expected_msg, bank_message, should_match, description)
        ('WMCZ ticket #12', 'WMCZ ticket #12', True, 'exact'),
        ('WMCZ ticket #12', 'PLATBA WMCZ ticket #12 faktura', True, 'embedded in longer text'),
        ('WMCZ ticket #12', 'WMCZ ticket #12, dekujeme', True, 'followed by punctuation'),
        ('WMCZ ticket #12', 'WMCZ ticket #12-faktura', True, 'followed by a hyphen'),
        ('WMCZ ticket #1', 'WMCZ ticket #12', False, 'prefix of a longer ticket number'),
        ('WMCZ ticket #1', 'WMCZ ticket #1234', False, 'prefix of a much longer number'),
        ('WMCZ ticket #12', 'WMCZ ticket #1', False, 'longer than the message reference'),
        ('WMCZ ticket #1', 'WMCZ ticket #31', False, 'different number sharing a digit'),
        ('WMCZ ticket #61', 'WMCZ ticket #61a', False, 'prefix of an alphanumeric accounting_info'),
        ('WMCZ ticket #61a', 'WMCZ ticket #61a', True, 'alphanumeric accounting_info'),
        # the trailing _ko already terminates the co-financing reference; these
        # cases are here so that nobody drops it as redundant
        ('Kofinancování ticketu #7_ko', 'Kofinancování ticketu #7_ko', True, 'co-financing exact'),
        ('Kofinancování ticketu #7_ko', 'Kofinancování ticketu #71_ko', False, 'co-financing prefix'),
        ('', 'WMCZ ticket #12', False, 'empty reference'),
        ('WMCZ ticket #12', '', False, 'empty bank message'),
        ('WMCZ ticket #12', None, False, 'missing bank message'),
    ]

    def test_message_matching(self):
        for expected_msg, message, should_match, description in self.CASES:
            with self.subTest(case=description):
                self.assertEqual(
                    FioPaymentManager._message_matches(expected_msg, message),
                    should_match,
                )


@override_settings(FIO_API_TOKENS={'2000145399/2010': 'mock_fio_token'})
class FioPaymentManagerTests(TestCase):
    def setUp(self):
        self.grant = Grant.objects.create(full_name='g', short_name='g', slug='g', source_bank_account='2000145399/2010')
        self.topic = Topic.objects.create(name='topic', grant=self.grant)
        self.ticket = Ticket.objects.create(name='T1', topic=self.topic)
        self.payment_info = PaymentInfo.objects.create(account_number='123456789/0300')
        self.expenditure = Expediture.objects.create(
            ticket=self.ticket,
            description='Platba faktury',
            amount=1000,
            payment_type=PaymentType.BANK_TRANSFER,
            payment_info=self.payment_info
        )

    def _imported_expenditure(self, accounting_info, order_number, amount=1000):
        """An expenditure already sent to Fio, and so a candidate for matching."""
        return Expediture.objects.create(
            ticket=self.ticket,
            description=f'expenditure {accounting_info}',
            amount=amount,
            payment_type=PaymentType.BANK_TRANSFER,
            accounting_info=accounting_info,
            payment_info=PaymentInfo.objects.create(account_number='123456789/0300'),
            import_info=ImportInfo.objects.create(order_number=order_number, due_date=datetime.date.today()),
        )

    @staticmethod
    def _fio_transaction(amount, message, order_number=None, account='123456789', bank='0300'):
        return {
            "column1": {"value": amount},  # amount
            "column2": {"value": account} if account else None,  # target account
            "column3": {"value": bank} if bank else None,  # bank code
            "column17": {"value": order_number} if order_number else None,  # ID instruction
            "column16": {"value": message} if message else None,  # msg
        }

    @staticmethod
    def _fio_response(*transactions):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "accountStatement": {"transactionList": {"transaction": list(transactions)}}
        }
        return response

    @patch('tracker.fio.requests.post')
    def test_process_expenditures_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<?xml version="1.0" encoding="UTF-8"?><response><result><status>ok</status><errorCode>0</errorCode><idInstruction>12345</idInstruction></result></response>'
        mock_post.return_value = mock_response

        manager = FioPaymentManager()
        report = manager.process_expenditures([self.expenditure], '2026-10-10')

        self.assertEqual(report['success_count'], 1)
        self.assertEqual(len(report['errors']), 0)

        self.expenditure.refresh_from_db()
        self.assertIsNotNone(self.expenditure.import_info)
        self.assertEqual(self.expenditure.import_info.order_number, '12345')

    @patch('tracker.fio.requests.post')
    def test_process_expenditures_rate_limit(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 409
        mock_post.return_value = mock_response

        manager = FioPaymentManager()
        report = manager.process_expenditures([self.expenditure], '2026-10-10')

        self.assertEqual(report['success_count'], 0)
        self.assertEqual(len(report['warnings']), 1)

        self.expenditure.refresh_from_db()
        self.assertIsNone(self.expenditure.import_info)

    @patch('tracker.fio.requests.post')
    def test_import_keeps_the_claim_when_the_result_is_unknown(self, mock_post):
        # A lost response does not tell us whether Fio took the order. The
        # expenditure must stay out of the queue, or the next import pays twice.
        mock_post.side_effect = requests.exceptions.ReadTimeout('timed out')

        report = FioPaymentManager().process_expenditures([self.expenditure], '2026-10-10')

        self.assertEqual(report['success_count'], 0)
        self.assertEqual(len(report['errors']), 1)

        self.expenditure.refresh_from_db()
        self.assertIsNotNone(self.expenditure.import_info)
        self.assertFalse(self.expenditure.import_info.error)
        self.assertEqual(self.expenditure.get_computed_state(), ExpenditureState.IMPORTED)

    @patch('tracker.fio.requests.post')
    def test_import_refuses_an_expenditure_that_is_already_imported(self, mock_post):
        self.expenditure.import_info = ImportInfo.objects.create(due_date=datetime.date.today())
        self.expenditure.save(update_fields=['import_info'])

        report = FioPaymentManager().process_expenditures([self.expenditure], '2026-10-10')

        mock_post.assert_not_called()
        self.assertEqual(report['success_count'], 0)
        self.assertEqual(len(report['warnings']), 1)

    @patch('tracker.fio.requests.post')
    def test_import_uses_a_timeout(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<?xml version="1.0" encoding="UTF-8"?><response><result><status>ok</status><errorCode>0</errorCode><idInstruction>12345</idInstruction></result></response>'
        mock_post.return_value = mock_response

        FioPaymentManager().process_expenditures([self.expenditure], '2026-10-10')

        self.assertEqual(mock_post.call_args.kwargs['timeout'], FioPaymentManager.HTTP_TIMEOUT)

    @patch('tracker.fio.requests.get')
    def test_sync_transactions_match(self, mock_get):
        self.expenditure.import_info = ImportInfo.objects.create(order_number='12345', due_date=datetime.date.today())
        self.expenditure.save()

        mock_get.return_value = self._fio_response(
            self._fio_transaction(-1000.0, f'WMCZ ticket #{self.ticket.id}', order_number='12345')
        )

        manager = FioPaymentManager()
        report = manager.sync_transactions(days_back=14, expiry_days=0)

        self.assertEqual(report['marked_paid'], 1)
        self.expenditure.refresh_from_db()
        self.assertTrue(self.expenditure.paid)

    @patch('tracker.fio.requests.get')
    def test_sync_transactions_card_match(self, mock_get):
        card_exp = Expediture.objects.create(
            ticket=self.ticket,
            description='card payment',
            amount=500,
            payment_type=PaymentType.CARD,
            accounting_info='61a'
        )

        mock_get.return_value = self._fio_response(
            self._fio_transaction(-500.0, 'WMCZ ticket #61a', account=None, bank=None)
        )

        manager = FioPaymentManager()
        report = manager.sync_transactions(days_back=14, expiry_days=0)

        self.assertEqual(report['marked_paid'], 1)
        card_exp.refresh_from_db()
        self.assertTrue(card_exp.paid)

    @patch('tracker.fio.requests.get')
    def test_sync_does_not_match_reference_prefix(self, mock_get):
        # _get_payment_message() prefers accounting_info over the ticket id, so
        # pinning it keeps the references stable whatever the auto-increment ids are.
        short = self._imported_expenditure(accounting_info='1', order_number='999')
        long_ref = self._imported_expenditure(accounting_info='12', order_number='999')

        mock_get.return_value = self._fio_response(
            self._fio_transaction(-1000.0, 'WMCZ ticket #12', order_number='999')
        )

        report = FioPaymentManager().sync_transactions(days_back=14, expiry_days=0)

        short.refresh_from_db()
        long_ref.refresh_from_db()
        self.assertFalse(short.paid, 'ticket #1 must not be paid by ticket #12 transaction')
        self.assertTrue(long_ref.paid)
        self.assertEqual(report['marked_paid'], 1)

    @patch('tracker.fio.requests.get')
    def test_sync_refuses_to_guess_between_identical_orders(self, mock_get):
        first = self._imported_expenditure(accounting_info='40', order_number='777')
        second = self._imported_expenditure(accounting_info='41', order_number='777')

        # same amount, same target account, same batch, and a bank message that
        # identifies neither -- there is nothing left to tell them apart, so
        # marking either one would be a guess
        mock_get.return_value = self._fio_response(
            self._fio_transaction(-1000.0, '', order_number='777')
        )

        report = FioPaymentManager().sync_transactions(days_back=14, expiry_days=0)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.paid)
        self.assertFalse(second.paid)
        self.assertEqual(report['marked_paid'], 0)
        self.assertEqual(len(report['errors']), 1)

    @patch('tracker.fio.requests.get')
    def test_sync_matches_amount_that_is_not_binary_exact(self, mock_get):
        # Decimal('10.10') != 10.1, so comparing the model amount against the raw
        # JSON float drops most real amounts with cents
        exp = self._imported_expenditure(accounting_info='77', order_number='555', amount=Decimal('10.10'))

        mock_get.return_value = self._fio_response(
            self._fio_transaction(-10.1, 'WMCZ ticket #77', order_number='555')
        )

        report = FioPaymentManager().sync_transactions(days_back=14, expiry_days=0)

        exp.refresh_from_db()
        self.assertTrue(exp.paid)
        self.assertEqual(report['marked_paid'], 1)

    @patch('tracker.fio.requests.get')
    def test_sync_matches_amount_with_cents_without_order_number(self, mock_get):
        # Fio does not return the order number for every transaction. Then the
        # amount and the target account must confirm the message, and so the
        # amount decides. Decimal('10.10') != 10.1, thus a comparison against
        # the raw JSON float drops the transaction.
        exp = self._imported_expenditure(accounting_info='78', order_number='556', amount=Decimal('10.10'))

        mock_get.return_value = self._fio_response(
            self._fio_transaction(-10.1, 'WMCZ ticket #78')
        )

        report = FioPaymentManager().sync_transactions(days_back=14, expiry_days=0)

        exp.refresh_from_db()
        self.assertTrue(exp.paid)
        self.assertEqual(report['marked_paid'], 1)

    @patch('tracker.fio.requests.get')
    def test_sync_matches_card_amount_with_cents(self, mock_get):
        # A card payment never has an order number, and so the amount always
        # decides.
        card_exp = Expediture.objects.create(
            ticket=self.ticket,
            description='card payment with cents',
            amount=Decimal('10.10'),
            payment_type=PaymentType.CARD,
            accounting_info='88a'
        )

        mock_get.return_value = self._fio_response(
            self._fio_transaction(-10.1, 'WMCZ ticket #88a', account=None, bank=None)
        )

        report = FioPaymentManager().sync_transactions(days_back=14, expiry_days=0)

        card_exp.refresh_from_db()
        self.assertTrue(card_exp.paid)
        self.assertEqual(report['marked_paid'], 1)

    @patch('tracker.fio.requests.get')
    def test_sync_uses_a_timeout(self, mock_get):
        mock_get.return_value = self._fio_response()

        FioPaymentManager().sync_transactions(days_back=14, expiry_days=0)

        self.assertEqual(mock_get.call_args.kwargs['timeout'], FioPaymentManager.HTTP_TIMEOUT)


class PaymentServiceTests(TestCase):
    def setUp(self):
        self.grant = Grant.objects.create(full_name='g', short_name='g', slug='g')
        self.topic = Topic.objects.create(name='topic', grant=self.grant)
        self.ticket = Ticket.objects.create(name='T1', topic=self.topic)

    def test_revert_import(self):
        exp = Expediture.objects.create(ticket=self.ticket, description='Test Revert', amount=100)
        exp.import_info = ImportInfo.objects.create(order_number='12345')
        exp.save()

        result = PaymentService.revert_import(exp.id)
        self.assertTrue(result)

        exp.refresh_from_db()
        self.assertIsNone(exp.import_info)

        exp.paid = True
        exp.import_info = ImportInfo.objects.create(order_number='99999')
        exp.save()

        with self.assertRaises(ValueError):
            PaymentService.revert_import(exp.id)

        exp2 = Expediture.objects.create(ticket=self.ticket, description='Test No Import', amount=200)
        result2 = PaymentService.revert_import(exp2.id)
        self.assertFalse(result2)


class CommandFiosyncTests(TestCase):
    @patch('tracker.fio.FioPaymentManager.sync_transactions')
    def test_fiosync_command_output(self, mock_sync):
        mock_sync.return_value = {
            'marked_paid': 2,
            'reverted': 1,
            'errors': ['Fio API error timeout']
        }

        out = io.StringIO()
        call_command('fiosync', days=10, expiry=3, stdout=out)
        output = out.getvalue()

        mock_sync.assert_called_once_with(days_back=10, expiry_days=3)

        self.assertIn('Starting Fio synchronization (history: 10 days, expiry after: 3 days)...', output)
        self.assertIn('Successfully matched and marked as PAID: 2 expenditures.', output)
        self.assertIn('Expired and reverted to WAITING: 1 expenditures.', output)
        self.assertIn('- Fio API error timeout', output)


class ExpeditureApiTests(TestCase):
    """The API must not be a way around the locks of the payment automation."""

    def setUp(self):
        self.password = 'secret'
        self.user = User.objects.create_user('apiuser', 'api@example.com', self.password)
        self.grant = Grant.objects.create(full_name='g', short_name='g', slug='g', source_bank_account='2000145399/2010')
        self.topic = Topic.objects.create(name='topic', grant=self.grant)
        self.ticket = Ticket.objects.create(name='T1', topic=self.topic, requested_user=self.user)
        self.expenditure = Expediture.objects.create(
            ticket=self.ticket,
            description='Platba faktury',
            amount=Decimal('1000.00'),
            payment_type=PaymentType.BANK_TRANSFER,
            payment_info=PaymentInfo.objects.create(account_number='123456789/0300'),
        )

    def _auth(self):
        """Use HTTP Basic, because it needs no CSRF token."""
        credentials = base64.b64encode(f'apiuser:{self.password}'.encode()).decode('ascii')
        return {'HTTP_AUTHORIZATION': f'Basic {credentials}'}

    def _detail_url(self, expenditure):
        return reverse('expediture-detail', kwargs={'pk': expenditure.id})

    def _mark_imported(self):
        self.expenditure.import_info = ImportInfo.objects.create(order_number='12345')
        self.expenditure.save(update_fields=['import_info'])

    def _patch(self, body):
        return self.client.patch(
            self._detail_url(self.expenditure),
            data=json.dumps(body),
            content_type='application/json',
            **self._auth()
        )

    def test_api_reads_an_expenditure_that_has_payment_details(self):
        # The API does not publish PaymentInfo and ImportInfo. A hyperlink to
        # them cannot resolve, thus these two fields must stay out of the API.
        self._mark_imported()

        response = self.client.get(self._detail_url(self.expenditure), **self._auth())

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('payment_info', response.json())
        self.assertNotIn('import_info', response.json())

    def test_api_refuses_to_change_an_imported_expenditure(self):
        self._mark_imported()

        response = self._patch({'amount': '9999.00'})

        self.assertEqual(response.status_code, 400)
        self.expenditure.refresh_from_db()
        self.assertEqual(self.expenditure.amount, Decimal('1000.00'))

    def test_api_cannot_clear_the_import_mark(self):
        # If the API clears the mark, the expenditure returns to the import
        # queue and the same order goes to the bank a second time.
        self._mark_imported()

        self._patch({'import_info': None})

        self.expenditure.refresh_from_db()
        self.assertIsNotNone(self.expenditure.import_info)
        self.assertEqual(self.expenditure.get_computed_state(), ExpenditureState.IMPORTED)

    def test_api_cannot_change_the_payment_type(self):
        response = self._patch({'payment_type': PaymentType.INTERNAL_TRANSFER})

        self.assertEqual(response.status_code, 200)
        self.expenditure.refresh_from_db()
        self.assertEqual(self.expenditure.payment_type, PaymentType.BANK_TRANSFER)

    def test_api_cannot_link_another_expenditure(self):
        # mark_paid() marks the linked expenditure as paid too. A link that a
        # user makes can thus mark the expenditure of another ticket as paid.
        other = Expediture.objects.create(ticket=self.ticket, description='other', amount=Decimal('5.00'))

        self._patch({'linked_expenditure': self._detail_url(other)})

        self.expenditure.refresh_from_db()
        self.assertIsNone(self.expenditure.linked_expenditure)

    def test_api_cannot_delete_a_paid_expenditure(self):
        self.expenditure.paid = True
        self.expenditure.save(update_fields=['paid'])

        response = self.client.delete(self._detail_url(self.expenditure), **self._auth())

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Expediture.objects.filter(id=self.expenditure.id).exists())
