from serializers import (
    User, UserSerializerAdmin, UserSerializer,
    TrackerProfile, TrackerProfileSerializer,
    Permission, PermissionSerializer,
    Group, GroupSerializer,
    Grant, GrantSerializer,
    Topic, TopicSerializer,
    Subtopic, SubtopicSerializer,
    Ticket, TicketSerializer, TicketNoAdminUpdateSerializer,
    MediaInfo, MediaInfoSerializer,
    Expediture, ExpeditureSerializer, ExpeditureAdminSerializer,
    Preexpediture, PreexpeditureSerializer,
    ContentTypeSerializer,
)
from rest_framework import viewsets
from rest_framework.response import Response
from permissions import ReadOnly, CanEditTicketElseReadOnly, CanEditExpedituresElseReadOnly, IsSelf
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import activate
from django.conf import settings

# ViewSets define the view behavior.


class ContentTypeViewSet(viewsets.ModelViewSet):
    queryset = ContentType.objects.all()
    serializer_class = ContentTypeSerializer
    permission_classes = (ReadOnly, )


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.none()
    filter_fields = ('is_active', 'is_staff', 'is_superuser')
    search_fields = ('first_name', 'last_name', 'username', 'email')

    def get_queryset(self):
        if self.request.user and self.request.user.is_staff:
            return User.objects.all()
        else:
            return User.objects.filter(is_active=True)

    def get_object(self):
        pk = self.kwargs.get('pk')

        if pk == "me" and self.request.user.is_authenticated():
            return self.request.user

        return super(UserViewSet, self).get_object()

    def get_serializer_class(self):
        if self.request.user and self.request.user.is_staff:
            return UserSerializerAdmin
        else:
            return UserSerializer


class TrackerProfileViewSet(viewsets.ModelViewSet):
    queryset = TrackerProfile.objects.none()
    serializer_class = TrackerProfileSerializer
    permission_classes = (IsSelf, )
    filter_fields = ('user', )

    def get_queryset(self):
        if self.request.user and self.request.user.is_staff:
            return TrackerProfile.objects.all()
        else:
            return TrackerProfile.objects.filter(user=self.request.user)

    def get_object(self):
        pk = self.kwargs.get('pk')

        if pk == "me" and self.request.user.is_authenticated():
            return self.request.user.trackerprofile

        return super(TrackerProfileViewSet, self).get_object()


class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = (ReadOnly, )


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
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


class LanguagesViewSet(viewsets.ViewSet):
    permission_classes = (ReadOnly, )

    def list(self, request):
        # If `lang` parameter is provided, then return proper localized language names. Otherwise return English names
        activate(request.GET.get('lang', 'en'))

        languages = dict(settings.LANGUAGES)

        return Response(languages)


class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.all()
    search_fields = ('summary', 'description')
    permission_classes = (CanEditTicketElseReadOnly, )

    def get_serializer_class(self):
        if (self.action == 'update' or self.action == 'create') and not self.request.user.is_staff:
            return TicketNoAdminUpdateSerializer
        return TicketSerializer

    def perform_create(self, serializer):
        serializer.save(requested_user=self.request.user)


class MediaInfoViewSet(viewsets.ModelViewSet):
    queryset = MediaInfo.objects.all()
    serializer_class = MediaInfoSerializer
    permission_classes = (CanEditExpedituresElseReadOnly, )
    filter_fields = ('ticket', )
    search_fields = ('description', 'url')


class ExpeditureViewSet(viewsets.ModelViewSet):
    queryset = Expediture.objects.all()
    permission_classes = (CanEditExpedituresElseReadOnly, )
    filter_fields = ('ticket', 'wage', 'paid')
    search_fields = ('description', 'accounting_info')

    def get_serializer_class(self):
        if not self.request.user.is_staff:
            return ExpeditureSerializer
        return ExpeditureAdminSerializer


class PreexpeditureViewSet(viewsets.ModelViewSet):
    queryset = Preexpediture.objects.all()
    serializer_class = PreexpeditureSerializer
    permission_classes = (CanEditExpedituresElseReadOnly, )
    filter_fields = ('ticket', 'wage')
    search_fields = ('description', )
