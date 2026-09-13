import hashlib

from socialauth.api import MediaWiki
from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings

# Number of seconds to remember that the MediaWiki tokens of a user are valid
OAUTH_VALID_CACHE_SECONDS = 600


def WarnIEUsers(get_response):
    def process_request(request):
        if 'HTTP_USER_AGENT' in request.META:
            user_agent = request.META['HTTP_USER_AGENT'].lower()
            request.is_IE = ('trident' in user_agent) or ('msie' in user_agent)

        return get_response(request)

    return process_request


def InvalidOauth(get_response):
    def process_request(request):
        response = get_response(request)

        if (
                request.method == 'GET' and not
                request.get_full_path().startswith('/api') and
                'oauth' not in request.get_full_path() and
                request.user.is_authenticated and
                settings.MEDIAINFO_MEDIAWIKI_API is not None
        ):
            # Verify MediaWiki token, if we have any to verify
            mw = MediaWiki(request.user)
            if mw.tokens:
                # The key contains the token, thus new tokens are verified again
                token_hash = hashlib.sha256(str(mw.tokens.get('oauth_token')).encode('utf-8')).hexdigest()
                cache_key = 'tracker:oauth-valid:%d:%s' % (request.user.id, token_hash)
                if cache.get(cache_key):
                    return response

                resp = mw.request({
                    "action": "query",
                    "meta": "userinfo"
                }, authorized_only=True).json()
                if resp.get('error', {}).get('code', "") == "mwoauth-invalid-authorization":
                    return redirect(reverse('invalid_oauth_tokens', kwargs={
                        'provider': 'mediawiki'
                    }) + "?next=" + request.path)
                if 'error' not in resp:
                    cache.set(cache_key, True, OAUTH_VALID_CACHE_SECONDS)
        return response

    return process_request
