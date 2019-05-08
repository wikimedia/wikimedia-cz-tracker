class WarnIEUsers():
    def process_request(self, request):
        if 'HTTP_USER_AGENT' in request.META:
            user_agent = request.META['HTTP_USER_AGENT'].lower()
            request.is_IE = ('trident' in user_agent) or ('msie' in user_agent)
