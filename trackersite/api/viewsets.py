from serializers import *
from rest_framework.permissions import IsAdminUser
from rest_framework import viewsets

# ViewSets define the view behavior.
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = (IsAdminUser, )

class TrackerProfileViewSet(viewsets.ModelViewSet):
    queryset = TrackerProfile.objects.all()
    serializer_class = TrackerProfileSerializer
    permission_classes = (IsAdminUser, )

class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = (IsAdminUser, )

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