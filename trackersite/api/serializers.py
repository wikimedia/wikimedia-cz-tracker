from django.contrib.auth.models import User, Group, Permission
from tracker.models import Ticket, Topic, Subtopic, Grant, MediaInfo, Expediture, Preexpediture, TrackerProfile
from rest_framework import serializers


# Serializers define the API representation.
class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        read_only_fields = ('last_login', 'date_joined')
        exclude = ('password', )


class TrackerProfileSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
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
    class Meta:
        model = Topic


class SubtopicSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Subtopic


class TicketSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        read_only_fields = ('state_str', 'updated', 'created', 'cluster', 'payment_status', 'imported')
        exclude = ('cluster', )
        model = Ticket


class MediaInfoSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = MediaInfo


class ExpeditureSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Expediture


class PreexpeditureSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Preexpediture
