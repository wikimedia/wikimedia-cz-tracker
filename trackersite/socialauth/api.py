from requests_oauthlib import OAuth1
import requests
from django.conf import settings


class MediaWiki():
    def __init__(self, user, api_url):
        self.user = user
        self.api_url = api_url

        provider = user.social_auth.filter(provider="mediawiki")
        if len(provider) == 1:
            self.tokens = provider.get().extra_data.get('access_token')
        else:
            self.tokens = None
        if self.tokens is None:
            raise ValueError("Given user isn't connected with any MediaWiki account.")

    def authorized_request(self, payload):
        return requests.post(
            self.api_url,
            payload,
            auth=OAuth1(
                settings.SOCIAL_AUTH_MEDIAWIKI_KEY,
                settings.SOCIAL_AUTH_MEDIAWIKI_SECRET,
                self.tokens.get('oauth_token'),
                self.tokens.get('oauth_token_secret')
            )
        )

    def get_token(self, type="csrf"):
        return self.authorized_request({
            "action": "query",
            "format": "json",
            "meta": "tokens",
            "type": type
        }).json()["query"]["tokens"]["%stoken" % type]
