from requests_oauthlib import OAuth1
import requests
import logging
import time
from django.conf import settings


class MediaWikiError(Exception):
    """ The MediaWiki API returned an error in the response body. """


class MediaWiki():
    # Seconds to wait for the connection and for each read from the API
    TIMEOUT = 60
    # HTTP status codes that can go away when the request is sent again
    RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
    # Maximum number of seconds to wait before a retry
    MAX_RETRY_WAIT = 120

    def __init__(self, user=None, api_url=None):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': settings.TRACKER_USER_AGENT})
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

    def _retry_wait(self, response, attempt):
        retry_after = response.headers.get('Retry-After') if response is not None else None
        if retry_after is not None and retry_after.isdigit():
            return min(int(retry_after), self.MAX_RETRY_WAIT)
        return min(5 * 2 ** attempt, self.MAX_RETRY_WAIT)

    def request(self, payload, method="POST", authorized_only=False, retries=0):
        """
        Send a request to the API.

        When retries is more than 0, send the request again after a connection
        error, a timeout or a status code in RETRY_STATUS_CODES.
        """
        kwargs = {"timeout": self.TIMEOUT}
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
        for attempt in range(retries + 1):
            try:
                if method == "POST":
                    r = self.session.post(self.api_url, data=payload, **kwargs)
                else:
                    r = self.session.get(self.api_url, params=payload, **kwargs)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                if attempt == retries:
                    raise
                time.sleep(self._retry_wait(None, attempt))
                continue
            if r.status_code in self.RETRY_STATUS_CODES and attempt < retries:
                logging.getLogger(__name__).warning(
                    f'API request to {self.api_url} failed with status {r.status_code}, retrying'
                )
                time.sleep(self._retry_wait(r, attempt))
                continue
            break
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            logging.getLogger(__name__).error(
                f'API request to {r.url} failed (status={r.status_code}, request_headers={r.request.headers}, response_headers={r.headers}, response={r.text}, user={self.user})'
            )
            raise
        return r

    def get_token(self, type="csrf"):
        return self.request({
            "action": "query",
            "format": "json",
            "meta": "tokens",
            "type": type
        }).json()["query"]["tokens"]["%stoken" % type]

    def get_content(self, page_id, rvslot="main"):
        payload = {
            "action": "query",
            "format": "json",
            "prop": "revisions",
            "pageids": [page_id],
            "rvprop": "content",
            "rvslots": rvslot
        }

        resp = self.request(payload).json()
        if "query" not in resp:
            return None
        data = resp["query"]["pages"]
        if "revisions" not in data[list(data.keys())[0]]:
            raise ValueError("The requested content doesn't exist")

        return data[list(data.keys())[0]]["revisions"][0]["slots"][rvslot]["*"]

    def get_contents(self, page_ids, rvslot="main", retries=0):
        """
        Get the current content of many pages with one request.

        The API gives the content of 50 pages for each request. Return a dict
        from page ID to content. The dict does not contain pages that do not
        exist or that have hidden content.
        """
        payload = {
            "action": "query",
            "formatversion": 2,
            "prop": "revisions",
            "pageids": "|".join(str(page_id) for page_id in page_ids),
            "rvprop": "content",
            "rvslots": rvslot
        }
        contents = {}
        while True:
            resp = self.request(payload, retries=retries).json()
            if "error" in resp:
                raise MediaWikiError(resp["error"])
            for page in resp.get("query", {}).get("pages", []):
                revisions = page.get("revisions")
                if "pageid" not in page or not revisions:
                    continue
                content = revisions[0].get("slots", {}).get(rvslot, {}).get("content")
                if content is not None:
                    contents[page["pageid"]] = content
            if "continue" not in resp:
                return contents
            payload = dict(payload, **resp["continue"])

    def put_content(self, page_id, text, summary="Automated update by Tracker", minor=False, retries=0):
        payload = {
            "action": "edit",
            "format": "json",
            "pageid": page_id,
            "text": text,
            "summary": summary,
            "token": self.get_token(),
            "minor": minor,
            "bot": True,
        }

        return self.request(payload, retries=retries)
