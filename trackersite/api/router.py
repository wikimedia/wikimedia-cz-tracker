from viewsets import (
    UserViewSet,
    PermissionViewSet,
    TrackerProfileViewSet,
    GroupViewSet,
    GrantViewSet,
    TopicViewSet,
    SubtopicViewSet,
    TicketViewSet,
    MediaInfoViewSet,
    ExpeditureViewSet,
    PreexpeditureViewSet,
    ContentTypeViewSet
)
from rest_framework import routers

# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r'contenttypes', ContentTypeViewSet)
router.register(r'auth/users', UserViewSet)
router.register(r'auth/permissions', PermissionViewSet)
router.register(r'auth/groups', GroupViewSet)
router.register(r'tracker/trackerprofile', TrackerProfileViewSet)
router.register(r'tracker/grants', GrantViewSet)
router.register(r'tracker/topics', TopicViewSet)
router.register(r'tracker/subtopics', SubtopicViewSet)
router.register(r'tracker/tickets', TicketViewSet)
router.register(r'tracker/mediainfo', MediaInfoViewSet)
router.register(r'tracker/expeditures', ExpeditureViewSet)
router.register(r'tracker/preexpeditures', PreexpeditureViewSet)
