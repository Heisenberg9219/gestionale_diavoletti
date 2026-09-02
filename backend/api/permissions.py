from rest_framework.permissions import BasePermission


def user_has_role(user, role_name):
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and user.status == user.Status.ACTIVE
        and (user.is_superuser or user.groups.filter(name=role_name).exists())
    )


class IsOwner(BasePermission):
    message = "Operazione riservata al titolare."

    def has_permission(self, request, view):
        return user_has_role(request.user, "Titolare")


class IsOwnerOrClerk(BasePermission):
    message = "Non disponi dei permessi necessari."

    def has_permission(self, request, view):
        return user_has_role(request.user, "Titolare") or user_has_role(
            request.user, "Commesso"
        )
