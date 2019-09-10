from requests_oauthlib import OAuth1
import requests
from django.conf import settings


class MediaWiki():
    def __init__(self, user=None, api_url=None):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Tracker (tracker@wikimedia.cz; https://tracker.wikimedia.cz)'})
        self.user = user
        if api_url:
            self.api_url = api_url
        else:
            self.api_url = settings.MEDIAINFO_MEDIAWIKI_API

        if self.user:
            provider = user.social_auth.filter(provider="mediawiki")
            if len(provider) == 1:
                self.tokens = provider.get().extra_data.get('access_token')
            else:
                self.tokens = None
        else:
            self.tokens = None
        if self.tokens is None:
            self.user = None      # Fail sliently, this user isn't connected with any MediaWiki account

    def request(self, payload, method="POST", authorized_only=False):
        kwargs = {}
        payload = dict(payload)  # Convert payload to dict explicitly, in case it's request.POST, which cannot be modified
        payload["format"] = "json"
        if self.user:
            kwargs["auth"] = OAuth1(
                settings.SOCIAL_AUTH_MEDIAWIKI_KEY,
                settings.SOCIAL_AUTH_MEDIAWIKI_SECRET,
                self.tokens.get('oauth_token'),
                self.tokens.get('oauth_token_secret')
            )
        elif authorized_only:
            raise ValueError("Given user isn't connected with any MediaWiki account and you require authorized request only.")
        if method == "POST":
            return self.session.post(self.api_url, data=payload, **kwargs)
        else:
            return self.session.get(self.api_url, params=payload, **kwargs)

    def get_token(self, type="csrf"):
        return self.request({
            "action": "query",
            "format": "json",
            "meta": "tokens",
            "type": type
        }).json()["query"]["tokens"]["%stoken" % type]

    def get_content(self, title, rvslot="main"):
        payload = {
            "action": "query",
            "format": "json",
            "prop": "revisions",
            "titles": title,
            "rvprop": "content",
            "rvslots": rvslot
        }

        data = self.request(payload).json()["query"]["pages"]
        if "revisions" not in data[list(data.keys())[0]]:
            raise ValueError("The requested content doesn't exist")

        return data[list(data.keys())[0]]["revisions"][0]["slots"][rvslot]["*"]

    def put_content(self, title, text, summary="Automated update by Tracker", minor=False):
        payload = {
            "action": "edit",
            "format": "json",
            "title": title,
            "text": text,
            "summary": summary,
            "token": self.get_token(),
            "minor": minor,
        }

        return self.request(payload)
