from django.contrib.auth.models import User, Group, Permission
from tracker.models import Ticket, Topic, Subtopic, Grant, MediaInfo, MediaInfoOld, Expediture, Preexpediture, TrackerProfile, TrackerPreferences
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext as _
from rest_framework import serializers
from tracker.views import TICKET_EXCLUDE_FIELDS


# Serializers define the API representation.
class ContentTypeSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = ContentType


class UserSerializerAdmin(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        read_only_fields = ('last_login', 'date_joined')
        exclude = ('password', )


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        exclude = ('password', 'email', "first_name", "last_name")


class TrackerPreferencesSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        read_only_fields = ('user', )
        fields = '__all__'
        model = TrackerPreferences


class TrackerProfileSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        read_only_fields = ('mediawiki_username', 'user')
        model = TrackerProfile


class GroupSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Group
        fields = ('id', 'name')


class PermissionSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Permission


class GrantSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Grant


class TopicSerializer(serializers.HyperlinkedModelSerializer):
    subtopics = serializers.SerializerMethodField()

    def get_subtopics(self, Topic):
        subtopics = []
        for subtopic in Topic.subtopic_set.all():
            subtopics.append({
                "id": subtopic.id,
                "name": subtopic.name,
                "display_name": unicode(subtopic)
            })
        return subtopics

    class Meta:
        model = Topic


class SubtopicSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Subtopic


class TicketSerializer(serializers.HyperlinkedModelSerializer):
    state_str = serializers.ReadOnlyField()

    class Meta:
        read_only_fields = ('media_updated', 'updated', 'created', 'cluster', 'payment_status', 'imported', 'is_completed')
        exclude = ('cluster', )
        model = Ticket


class TicketNoAdminUpdateSerializer(serializers.HyperlinkedModelSerializer):
    state_str = serializers.ReadOnlyField()

    def validate_deposit(self, deposit):
        if self.instance is None:
            # Ticket is not yet created
            if not deposit == 0.00:
                raise serializers.ValidationError(_('Deposit should be zero when creating a ticket'))
        else:
            if 'precontent' in Ticket.objects.get(id=self.instance.id).ack_set():
                raise serializers.ValidationError(_('Cannot edit deposit once a ticket has been preaccepted'))
            # Ticket is already created and will be updated
            preexpeditures_amount = Ticket.objects.get(id=self.instance.id).preexpeditures()['amount']
            if preexpeditures_amount is None:
                if not deposit == 0.00:
                    raise serializers.ValidationError(_('Deposit should be lower or equal to the sum of preexpeditures'))
            else:
                if not deposit <= preexpeditures_amount:
                    raise serializers.ValidationError(_('Deposit should be lower or equal to the sum of preexpeditures'))
        return deposit

    class Meta:
        read_only_fields = TICKET_EXCLUDE_FIELDS
        exclude = ('cluster', )
        model = Ticket


class MediaInfoSerializer(serializers.HyperlinkedModelSerializer):
    topic = serializers.SerializerMethodField()
    descriptionurl = serializers.SerializerMethodField()

    def get_descriptionurl(self, instance):
        return instance.mediawiki_link()

    def get_topic(self, instance):
        return instance.ticket.topic.name

    def validate_ticket(self, ticket):
        request_user = self.context['request'].user
        if self.instance is None and not (request_user.has_perm('tracker.add_mediainfo') or ticket.can_edit(request_user)):
            raise serializers.ValidationError(_('You can not add media to this ticket.'))
        if self.instance is not None and not (request_user.has_perm('tracker.change_mediainfo') or ticket.can_edit(request_user)):
            raise serializers.ValidationError(_('You can not edit the media of this ticket.'))
        return ticket

    class Meta:
        read_only_fields = ('categories', 'width', 'height', 'usages', 'canonicaltitle', 'thumb_url')
        model = MediaInfo


class MediaInfoOldSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = MediaInfoOld


class ExpeditureAdminSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Expediture


class ExpeditureSerializer(serializers.HyperlinkedModelSerializer):

    def validate_ticket(self, ticket):
        request_user = self.context['request'].user
        if self.instance is None and not (request_user.has_perm('tracker.add_expediture') or (ticket.can_edit(request_user)) and 'content' not in ticket.ack_set()):
            raise serializers.ValidationError(_('You can not add expiditures to this ticket.'))
        if self.instance is not None and not (request_user.has_perm('tracker.change_expediture') or (ticket.can_edit(request_user)) and 'content' not in ticket.ack_set()):
            raise serializers.ValidationError(_('You can not edit expiditures of this ticket.'))
        return ticket

    class Meta:
        read_only_fields = ('accounting_info', 'paid')
        model = Expediture


class PreexpeditureSerializer(serializers.HyperlinkedModelSerializer):

    def validate_ticket(self, ticket):
        request_user = self.context['request'].user
        if self.instance is None and not (request_user.has_perm('tracker.add_preexpediture') or (ticket.can_edit(request_user) and 'precontent' not in ticket.ack_set())):
            raise serializers.ValidationError(_('You can not add preexpiditures to this ticket.'))
        if self.instance is not None and not (request_user.has_perm('tracker.change_preexpediture') or (ticket.can_edit(request_user) and 'precontent' not in ticket.ack_set())):
            raise serializers.ValidationError(_('You can not edit preexpiditures of this ticket.'))
        return ticket

    class Meta:
        model = Preexpediture
