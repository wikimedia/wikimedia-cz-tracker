from serializers import *
from rest_framework.permissions import IsAdminUser
from rest_framework import viewsets


# ViewSets define the view behavior.
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = (IsAdminUser, )
    filter_fields = ('is_active', 'is_staff', 'is_superuser')
    search_fields = ('first_name', 'last_name', 'username', 'email')


class TrackerProfileViewSet(viewsets.ModelViewSet):
    queryset = TrackerProfile.objects.all()
    serializer_class = TrackerProfileSerializer
    permission_classes = (IsAdminUser, )
    filter_fields = ('user', )


class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = (IsAdminUser, )
    search_fields = ('name', )


class GrantViewSet(viewsets.ModelViewSet):
    queryset = Grant.objects.all()
    serializer_class = GrantSerializer


class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer
    filter_fields = ('grant', 'open_for_tickets', 'ticket_media', 'ticket_expenses', 'ticket_preexpenses')
    search_fields = ('name', 'description', 'form_description')


class SubtopicViewSet(viewsets.ModelViewSet):
    queryset = Subtopic.objects.all()
    serializer_class = SubtopicSerializer
    filter_fields = ('topic', )
    search_fields = ('name', 'description')


class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    search_fields = ('summary', 'description')


class MediaInfoViewSet(viewsets.ModelViewSet):
    queryset = MediaInfo.objects.all()
    serializer_class = MediaInfoSerializer
    filter_fields = ('ticket', )
    search_fields = ('description', 'url')


class ExpeditureViewSet(viewsets.ModelViewSet):
    queryset = Expediture.objects.all()
    serializer_class = ExpeditureSerializer
    filter_fields = ('ticket', 'wage', 'paid')
    search_fields = ('description', 'accounting_info')


class PreexpeditureViewSet(viewsets.ModelViewSet):
    queryset = Preexpediture.objects.all()
    serializer_class = PreexpeditureSerializer
    filter_fields = ('ticket', 'wage')
    search_fields = ('description', )
