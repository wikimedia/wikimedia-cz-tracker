from django.contrib.auth.models import User, Group, Permission
from tracker.models import Ticket, Topic, Subtopic, Grant, MediaInfo, Expediture, Preexpediture, TrackerProfile
from rest_framework import routers, serializers, viewsets

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
        model  = Group
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

# ViewSets define the view behavior.
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class TrackerProfileViewSet(viewsets.ModelViewSet):
    queryset = TrackerProfile.objects.all()
    serializer_class = TrackerProfileSerializer

class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer

class GrantViewSet(viewsets.ModelViewSet):
    queryset = Grant.objects.all()
    serializer_class = GrantSerializer

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer

class SubtopicViewSet(viewsets.ModelViewSet):
    queryset = Subtopic.objects.all()
    serializer_class = SubtopicSerializer

class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer

class MediaInfoViewSet(viewsets.ModelViewSet):
    queryset = MediaInfo.objects.all()
    serializer_class = MediaInfoSerializer

class ExpeditureViewSet(viewsets.ModelViewSet):
    queryset = Expediture.objects.all()
    serializer_class = ExpeditureSerializer

class PreexpeditureViewSet(viewsets.ModelViewSet):
    queryset = Preexpediture.objects.all()
    serializer_class = PreexpeditureSerializer

# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r'auth/users', UserViewSet)
router.register(r'auth/permissions', PermissionViewSet)
router.register(r'tracker/trackerprofile', TrackerProfileViewSet)
router.register(r'auth/groups', GroupViewSet)
router.register(r'tracker/grants', GrantViewSet)
router.register(r'tracker/topics', TopicViewSet)
router.register(r'tracker/subtopics', SubtopicViewSet)
router.register(r'tracker/tickets', TicketViewSet)
router.register(r'tracker/mediainfo', MediaInfoViewSet)
router.register(r'tracker/expeditures', ExpeditureViewSet)
router.register(r'tracker/preexpeditures', PreexpeditureViewSet)