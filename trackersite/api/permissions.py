from rest_framework.permissions import SAFE_METHODS, BasePermission


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


class CanEditTicketElseReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.has_perm('tracker.add_ticket') and request.user.has_perm('tracker.change_ticket'):
            return True
        if request.method in SAFE_METHODS:
            return True
        return obj.can_edit(request.user)


class CanEditExpedituresElseReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.has_perm('tracker.add_expediture') and request.user.has_perm('tracker.change_expediture'):
            return True
        if request.method in SAFE_METHODS:
            return True
        return obj.ticket.can_edit(request.user)


class CanEditMediaElseReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.ticket.can_edit(request.user)


class IsSelf(BasePermission):
    def has_permission(self, request, view):
        if request.method == "POST" and not request.user.has_perm('tracker.add_trackerprofile'):
            return False
        return True

    def has_object_permission(self, request, view, obj):
        return obj.user == request.user or request.user.has_perm('tracker.change_trackerprofile')
