from socialauth.api import MediaWiki
from django.shortcuts import redirect
from django.core.urlresolvers import reverse
from django.conf import settings


class WarnIEUsers():
    def process_request(self, request):
        if 'HTTP_USER_AGENT' in request.META:
            user_agent = request.META['HTTP_USER_AGENT'].lower()
            request.is_IE = ('trident' in user_agent) or ('msie' in user_agent)


class InvalidOauth():
    def process_request(self, request):
        if (
            request.method == 'GET' and not
            request.get_full_path().startswith('/api') and
            'oauth' not in request.get_full_path() and
            request.user.is_authenticated() and
            settings.MEDIAINFO_MEDIAWIKI_API is not None
        ):
            # Verify MediaWiki token, if we have any to verify
            mw = MediaWiki(request.user)
            if mw.tokens:
                resp = mw.request({
                    "action": "query",
                    "meta": "userinfo"
                }, authorized_only=True).json()
                if resp.get('error', {}).get('code', "") == "mwoauth-invalid-authorization":
                    return redirect(reverse('invalid_oauth_tokens', kwargs={
                        'provider': 'mediawiki'
                    }))
