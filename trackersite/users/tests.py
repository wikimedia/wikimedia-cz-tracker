# -*- coding: utf-8 -*-
import os
from django.core import mail
from django.test import TestCase
from django.test.client import Client
from django.urls import reverse

from django.contrib.auth.models import User

from tracker.models import TrackerProfile


class CreateUserTest(TestCase):
    def setUp(self):
        os.environ['RECAPTCHA_DISABLE'] = 'True'

    def tearDown(self):
        try:
            del os.environ['RECAPTCHA_DISABLE']
        except KeyError:
            # sometimes deleted for tests
            pass

    def test_user_registration_captcha(self):
        del os.environ['RECAPTCHA_DISABLE']
        USERNAME, PW, EMAIL = 'foouser', 'foo', 'foo@example.com'
        response = Client().post(reverse('register'), {
            'username': USERNAME, 'password1': PW, 'password2': PW, 'email': EMAIL,
        })
        self.assertEqual(200, response.status_code)

        # user does not exist -> we've been killed by captcha
        self.assertEqual(0, len(User.objects.filter(username=USERNAME)))

    def register(self, client):
        USERNAME, PW, EMAIL = 'foouser', 'foo', 'foo@example.com'
        response = client.post(reverse('register'), {
            'username': USERNAME, 'password1': PW, 'password2': PW, 'email': EMAIL,
        }, follow=True)
        self.assertRedirects(response, reverse("fill_details"))
        self.assertEqual(1, len(User.objects.filter(username=USERNAME)))

        return User.objects.get(username=USERNAME)

    def test_signup_process(self):
        c = Client()
        user = self.register(c)

        NAME, PREFIX, NUMBER, BANK = 'My account', '19', '2000145399', '0800'
        CONTACT, ID = 'bar', 'baz'
        response = c.post(reverse('fill_details'), {
            'name': NAME,
            'prefix': PREFIX,
            'number': NUMBER,
            'bank': BANK,
            'other_contact': CONTACT,
            'other_identification': ID
        }, follow=True)
        self.assertRedirects(response, reverse("ticket_list"))
        self.assertEqual(1, len(TrackerProfile.objects.filter(user=user, other_contact=CONTACT, other_identification=ID)))

        account = user.trackerprofile.bank_accounts.get()
        self.assertEqual(account.name, NAME)
        self.assertEqual(account.full_number, '19-2000145399/0800')

        # the deprecated text field stays empty
        self.assertEqual(user.trackerprofile.bank_account, '')

    def test_signup_process_without_bank_account(self):
        c = Client()
        user = self.register(c)

        CONTACT, ID = 'bar', 'baz'
        response = c.post(reverse('fill_details'), {
            'name': '',
            'prefix': '',
            'number': '',
            'bank': '',
            'other_contact': CONTACT,
            'other_identification': ID
        }, follow=True)
        self.assertRedirects(response, reverse("ticket_list"))
        self.assertEqual(1, len(TrackerProfile.objects.filter(user=user, other_contact=CONTACT, other_identification=ID)))
        self.assertEqual(0, user.trackerprofile.bank_accounts.count())

    def test_signup_process_with_incomplete_bank_account(self):
        c = Client()
        user = self.register(c)

        response = c.post(reverse('fill_details'), {
            'name': '',
            'prefix': '',
            'number': '2000145399',
            'bank': '',
            'other_contact': 'bar',
            'other_identification': 'baz'
        })
        self.assertEqual(200, response.status_code)
        self.assertIn('name', response.context['form'].errors)
        self.assertIn('bank', response.context['form'].errors)
        self.assertEqual(0, user.trackerprofile.bank_accounts.count())


class PasswordResetTests(TestCase):
    def test_password_reset(self):
        response = Client().get(reverse("password_reset"))
        self.assertEqual(200, response.status_code)

    def test_password_reset_requested(self):
        USERNAME, PW, EMAIL = 'foouser', 'foo', 'foo@example.com'
        u = User.objects.create(username=USERNAME, email=EMAIL)
        u.set_password(PW)
        u.save()

        response = Client().post(reverse("password_reset"), {
            'email': EMAIL,
        })
        self.assertRedirects(response, reverse("password_reset_done"))

        # sent an e-mail
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_done(self):
        response = Client().get(reverse("password_reset_done"))
        self.assertEqual(200, response.status_code)

    def test_password_reset_confirm(self):
        response = Client().get(reverse("password_reset_confirm", kwargs={
            'uidb64': 'a', 'token': 'a',
        }))
        self.assertEqual(200, response.status_code)

    def test_password_reset_complete(self):
        response = Client().get(reverse("password_reset_complete"))
        self.assertEqual(200, response.status_code)
