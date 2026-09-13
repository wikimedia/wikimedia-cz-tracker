import datetime
import logging
import re
from collections import Counter, OrderedDict

import requests
from django.conf import settings
from django.utils.functional import cached_property

from socialauth.api import MediaWiki, MediaWikiError

logger = logging.getLogger(__name__)


class MediaInfoSync:
    """
    Synchronize the media of tickets with MediaWiki.

    Get the data of the files from MediaWiki, and store it in the tracker.
    Add the tracker template to the MediaWiki pages of the files.

    tracker.models imports this module, thus this module does not import
    tracker.models. It gets the models from the objects that it receives.
    """

    # The MediaWiki API gives scaled thumbnails and page contents for 50 pages in each request
    BATCH_SIZE = 50
    # Number of times to send a failed MediaWiki request again
    RETRIES = 3
    THUMBNAIL_WIDTH = 200
    # Errors of a MediaWiki request. The request can fail, or the response can have an unexpected format.
    ERRORS = (requests.exceptions.RequestException, MediaWikiError, ValueError, KeyError)

    def __init__(self, user=None):
        """ The user reads and edits the pages to change the templates. """
        self.user = user

    @cached_property
    def reader(self):
        """ The MediaWiki client that gets the data of the files. """
        return MediaWiki(user=None)

    @cached_property
    def editor(self):
        """ The MediaWiki client that reads and edits the pages of the user. """
        return MediaWiki(self.user, settings.MEDIAINFO_MEDIAWIKI_API)

    @staticmethod
    def _raise_for_errors(errors):
        if errors:
            raise MediaWikiError('%d of the MediaWiki requests failed' % len(errors)) from errors[-1]

    def _fetch_in_batches(self, keys, fetch, results, failed_keys):
        """
        Call fetch for each batch of keys, and add its result to results.

        When a batch fails, add its keys to failed_keys and continue.
        Return the list of errors.
        """
        errors = []
        for i in range(0, len(keys), self.BATCH_SIZE):
            batch = keys[i:i + self.BATCH_SIZE]
            try:
                results.update(fetch(batch))
            except self.ERRORS as e:
                logger.exception('MediaWiki request for %d pages failed' % len(batch))
                failed_keys.update(batch)
                errors.append(e)
        return errors

    # Templates

    @staticmethod
    def templates_enabled():
        return bool(settings.MEDIAINFO_MEDIAWIKI_TEMPLATE and settings.MEDIAINFO_MEDIAWIKI_INFO_TEMPLATE)

    @staticmethod
    def get_template(media):
        """ Return the template that marks the media on MediaWiki. """
        parameters_unsorted = {
            'rok': datetime.date.today().year,
            'podtéma': media.ticket.subtopic or '',
            'tiket': media.ticket.id,
        }
        if media.created is not None:
            parameters_unsorted['rok'] = media.created.year
        parameters = OrderedDict(sorted(parameters_unsorted.items(), key=lambda t: t[0]))

        template = '{{%s' % settings.MEDIAINFO_MEDIAWIKI_TEMPLATE
        for param in parameters:
            template += "|%s=%s" % (param, str(parameters[param]))
        template += '}}'
        return template

    @staticmethod
    def strip_template(text):
        # TODO: First letter of template should be case-insensitive
        regex = r"\n?{{" + settings.MEDIAINFO_MEDIAWIKI_TEMPLATE + r"[^}]*}}"
        return re.sub(regex, "", text)

    @staticmethod
    def get_template_end_position(text, template):
        # TODO: First letter of template should be case-insensitive
        opening_tag = "{{" + template
        if opening_tag not in text:
            return -1

        position = text.find(opening_tag)
        open_brackets = 0

        for idx in range(position, len(text) - 1):
            if text[idx] == '{':
                open_brackets += 1
            elif text[idx] == '}':
                open_brackets -= 1
            if open_brackets == 0:
                return idx + 1

        return -1

    @staticmethod
    def add_template(text, template):
        """
        Add the template to the page text.

        Return a tuple of the new text and of the minor flag for the edit.
        When the text contains the template already, return (None, None).
        """
        if template in text:
            return None, None

        text = MediaInfoSync.strip_template(text)
        insert_to = MediaInfoSync.get_template_end_position(text, settings.MEDIAINFO_MEDIAWIKI_INFO_TEMPLATE)
        if insert_to != -1:
            return text[:insert_to] + u"\n" + template + text[insert_to:], False
        return text + u"\n" + template, True

    def add_template_to_page(self, media):
        """ Add the template to the MediaWiki page of one media. """
        if not self.templates_enabled():
            return

        old = self.editor.get_content(media.page_id)
        if old is None:
            return

        new, minor = self.add_template(old, self.get_template(media))
        if new is not None:
            logger.info('Adding MediaInfo %d to MediaWiki by user %s' % (media.id, getattr(self.user, 'id', None)))
            self.editor.put_content(media.page_id, new, minor=minor)

    def remove_template_from_page(self, page_id):
        """ Remove the template from a MediaWiki page. """
        if not self.templates_enabled():
            return

        logger.info('Removing MediaInfo %d from MediaWiki by user %s' % (page_id, getattr(self.user, 'id', None)))
        try:
            self.editor.put_content(page_id, self.strip_template(self.editor.get_content(page_id)), minor=True)
        except ValueError:
            # the edited page doesn't exist, ignore
            pass

    def add_templates(self, medias):
        """
        Add the template to the MediaWiki pages of the medias that do not have it.

        Read the pages in batches, and edit only the pages that change. When a
        request fails, continue with the other pages, and then raise
        MediaWikiError.
        """
        if not self.templates_enabled():
            return

        medias_by_page_id = {}
        for media in medias:
            if media.page_id and media.page_id > 0:
                medias_by_page_id.setdefault(media.page_id, media)

        errors = []
        page_ids = sorted(medias_by_page_id)
        for i in range(0, len(page_ids), self.BATCH_SIZE):
            batch = page_ids[i:i + self.BATCH_SIZE]
            try:
                contents = self.editor.get_contents(batch, retries=self.RETRIES)
            except self.ERRORS as e:
                logger.exception('Cannot read %d MediaWiki pages' % len(batch))
                errors.append(e)
                continue

            for page_id in batch:
                if page_id not in contents:
                    # The page does not exist
                    continue
                media = medias_by_page_id[page_id]
                new, minor = self.add_template(contents[page_id], self.get_template(media))
                if new is None:
                    continue
                logger.info('Adding MediaInfo %d to MediaWiki by user %s' % (media.id, getattr(self.user, 'id', None)))
                try:
                    self.editor.put_content(page_id, new, minor=minor, retries=self.RETRIES)
                except self.ERRORS as e:
                    logger.exception('Cannot edit MediaWiki page %d' % page_id)
                    errors.append(e)
        self._raise_for_errors(errors)

    # File data

    def fetch_data(self, page_ids, width=None):
        """
        Get the MediaWiki data of up to BATCH_SIZE files.

        Send one request, and more requests when a file has more categories or
        usages than one response can contain. Return a dict from page ID to
        data. The dict does not contain the pages that are not files.
        """
        module_parameters = {
            "imageinfo": {"iiprop": "dimensions|url|canonicaltitle"},
            "categories": {"clprop": "hidden", "cllimit": "max"},
            "globalusage": {"gulimit": "max"},
        }
        if width:
            module_parameters["imageinfo"]["iiurlwidth"] = width

        def make_payload(props, continuation):
            payload = {
                "action": "query",
                "formatversion": 2,
                "pageids": "|".join(str(page_id) for page_id in page_ids),
                "prop": "|".join(props),
            }
            for prop in props:
                payload.update(module_parameters[prop])
            payload.update(continuation)
            return payload

        payload = make_payload(["imageinfo", "categories", "globalusage"], {})

        pages = {}
        while True:
            resp = self.reader.request(payload, retries=self.RETRIES).json()
            if 'error' in resp:
                raise MediaWikiError(resp['error'])
            for page in resp.get('query', {}).get('pages', []):
                if 'pageid' not in page:
                    continue
                data = pages.setdefault(page['pageid'], {'categories': [], 'globalusage': []})
                if page.get('imageinfo') and 'imageinfo' not in data:
                    data['imageinfo'] = page['imageinfo'][0]
                data['categories'].extend(page.get('categories', []))
                data['globalusage'].extend(page.get('globalusage', []))

            # Continue only the categories and the usages. For a request with
            # one file, the API also continues to the old versions of the file.
            continuation = {}
            props = []
            for key, prop in (('clcontinue', 'categories'), ('gucontinue', 'globalusage')):
                if key in resp.get('continue', {}):
                    continuation[key] = resp['continue'][key]
                    props.append(prop)
            if not props:
                break
            payload = make_payload(props, continuation)

        result = {}
        for page_id, data in pages.items():
            imageinfo = data.get('imageinfo')
            if imageinfo is None:
                continue
            result[page_id] = {
                "url": (imageinfo.get('thumburl') if width else None) or imageinfo['url'],
                "page_title": imageinfo['canonicaltitle'],
                'width': imageinfo.get('width'),
                'height': imageinfo.get('height'),
                'categories': data['categories'],
                'globalusage': data['globalusage'],
            }
        return result

    def fetch_page_ids(self, titles):
        """
        Get the page IDs of up to BATCH_SIZE titles.

        Return a dict from title to page ID. The page ID is None when the page
        does not exist.
        """
        resp = self.reader.request({
            "action": "query",
            "formatversion": 2,
            "titles": "|".join(titles),
        }, retries=self.RETRIES).json()
        if 'error' in resp:
            raise MediaWikiError(resp['error'])
        query = resp.get('query', {})
        normalized = {item['from']: item['to'] for item in query.get('normalized', [])}
        pages = {page['title']: page for page in query.get('pages', [])}

        page_ids = {}
        for title in titles:
            page = pages.get(normalized.get(title, title), {})
            if page.get('missing') or page.get('invalid'):
                page_ids[title] = None
            else:
                page_ids[title] = page.get('pageid')
        return page_ids

    def refresh(self, medias):
        """
        Get the MediaWiki data of the medias, and store the changes.

        Delete the medias whose files do not exist. Send the requests in
        batches. When a batch fails, do not change its medias, continue with
        the other batches, and then raise MediaWikiError.
        """
        medias = list(medias)

        def fetch_data(page_ids):
            return self.fetch_data(page_ids, width=self.THUMBNAIL_WIDTH)

        data = {}
        failed_page_ids = set()
        page_ids = sorted({media.page_id for media in medias if media.page_id and media.page_id > 0})
        errors = self._fetch_in_batches(page_ids, fetch_data, data, failed_page_ids)

        # A media can have no page ID, or a page ID that is not a file now. For
        # example, a file that was deleted and uploaded again has a new page ID.
        # Find the page ID from the title.
        titles = sorted({
            media.page_title for media in medias
            if media.page_title and media.page_id not in data and media.page_id not in failed_page_ids
        })
        page_ids_by_title = {}
        failed_titles = set()
        errors += self._fetch_in_batches(titles, self.fetch_page_ids, page_ids_by_title, failed_titles)
        new_page_ids = sorted({
            page_id for page_id in page_ids_by_title.values()
            if page_id and page_id not in data and page_id not in failed_page_ids
        })
        errors += self._fetch_in_batches(new_page_ids, fetch_data, data, failed_page_ids)

        for media in medias:
            if media.page_id in failed_page_ids:
                continue
            if media.page_id in data:
                self._store_data(media, data[media.page_id])
                continue
            if not media.page_title or media.page_title in failed_titles:
                continue
            new_page_id = page_ids_by_title.get(media.page_title)
            if new_page_id in failed_page_ids:
                continue
            if new_page_id not in data:
                # The file does not exist
                media.delete()
                continue
            media.page_id = new_page_id
            self._store_data(media, data[new_page_id], force_save=True)
        self._raise_for_errors(errors)

    def refresh_ticket(self, ticket):
        """ Refresh all the media of the ticket, and store the time of the refresh. """
        medias = ticket.mediainfo_set.prefetch_related('mediainfocategory_set', 'mediainfousage_set')
        try:
            self.refresh(medias)
        finally:
            # The refresh can delete media, thus the cached media counts can change
            ticket.flush_cache()

        # Do not use ticket.save(). It writes all the fields from the old copy of the ticket.
        type(ticket).objects.filter(pk=ticket.pk).update(media_updated=datetime.datetime.now(tz=datetime.timezone.utc))

    @staticmethod
    def _sync_related_rows(media, rows, fields, wanted):
        """ Delete and create related rows, so that they match the wanted tuples of field values. """
        model = rows.model
        missing = Counter(wanted)
        obsolete = []
        for row in rows:
            key = tuple(getattr(row, field) for field in fields)
            if missing[key] > 0:
                missing[key] -= 1
            else:
                obsolete.append(row.pk)
        if obsolete:
            model.objects.filter(pk__in=obsolete).delete()
        new_rows = [
            model(mediainfo=media, **dict(zip(fields, key)))
            for key, count in missing.items() for _ in range(count)
        ]
        if new_rows:
            model.objects.bulk_create(new_rows)

    def _store_data(self, media, data, force_save=False):
        """ Store the data from fetch_data() in the media. Write only the values that change. """
        changed = force_save
        for field, value in (
                ('thumb_url', data['url']),
                ('page_title', data['page_title']),
                ('width', data.get('width')),
                ('height', data.get('height')),
        ):
            if getattr(media, field) != value:
                setattr(media, field, value)
                changed = True
        if changed:
            media.save(no_update=True)
            if media.pk is None:
                # save() deleted this media, because the ticket has a media with the same title
                return

        self._sync_related_rows(
            media, media.mediainfocategory_set.all(), ('title', ),
            [(category['title'], ) for category in data.get('categories', []) if not category.get('hidden')]
        )
        self._sync_related_rows(
            media, media.mediainfousage_set.all(), ('url', 'title', 'project'),
            [(usage['url'], usage['title'], usage['wiki']) for usage in data.get('globalusage', [])]
        )
