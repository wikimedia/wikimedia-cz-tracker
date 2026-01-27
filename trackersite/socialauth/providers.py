from social_core.backends.mediawiki import MediaWiki


class MediaWikiWithUA(MediaWiki):
    SEND_USER_AGENT = True
