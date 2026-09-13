from rest_framework.permissions import BasePermission, SAFE_METHODS


PAGE_PATHS = (
    ("/gift-lists/", "Liste regalo"), ("/customers/", "Clienti"),
    ("/vouchers/", "Buoni"), ("/loyalty/", "Fedeltà"),
    ("/reorders/", "Riordini"), ("/returns/", "Resi"),
    ("/suppliers/", "Fornitori"), ("/purchasing/", "Ordini acquisto"),
    ("/promotions/", "Promozioni"), ("/expenses/", "Spese"),
    ("/documents/", "Documenti e OCR"), ("/notifications/", "Notifiche"),
    ("/catalog/", "Catalogo"), ("/pricing/", "Catalogo"),
    ("/integrations/", "Integrazioni"), ("/reporting/", "Report"),
)

OWNER_ONLY_PAGES = {"Integrazioni", "Report"}


def page_permission_for_request(request):
    path = request.path
    if "/inventory/count" in path:
        return "Inventari"
    if "/inventory/" in path:
        return "Magazzino"
    if "/reporting/overview/" in path:
        return "Panoramica"
    if "/sales/cash" in path:
        return "Cassa"
    if "/sales/" in path:
        return "Storico vendite" if request.method in SAFE_METHODS else "Nuova vendita"
    for fragment, page in PAGE_PATHS:
        if fragment in path:
            return page
    return None


def permission_action_for_request(request):
    if request.method in SAFE_METHODS:
        return "can_view"
    if request.method == "DELETE" or any(value in request.path for value in ("/remove/", "/cancel/", "/archive/")):
        return "can_delete"
    if request.method in {"PATCH", "PUT"} or any(value in request.path for value in (
        "/update", "/change", "/complete", "/close", "/resolve", "/confirm",
        "/finalize", "/send", "/activate", "/end", "/link-", "/process",
        "/mark-read",
    )):
        return "can_update"
    return "can_create"


def clerk_has_page_permission(request):
    page = page_permission_for_request(request)
    if "/core/" in request.path:
        return request.method in SAFE_METHODS
    if page is None or page in OWNER_ONLY_PAGES:
        return False

    from accounts.models import UserPagePermission

    pages = (page,)
    # Le schermate operative possono leggere una vendita per completare un reso
    # o una nuova vendita, senza concedere l'accesso allo storico completo.
    if page == "Storico vendite" and "/sales/" in request.path and request.method in SAFE_METHODS:
        pages = ("Storico vendite", "Nuova vendita", "Resi")

    return UserPagePermission.objects.filter(
        user=request.user,
        page_key__in=pages,
        **{permission_action_for_request(request): True},
    ).exists()


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
        if user_has_role(request.user, "Titolare"):
            return True
        return user_has_role(request.user, "Commesso") and clerk_has_page_permission(request)


class OwnerWriteClerkRead(BasePermission):
    message = "Non disponi dei permessi necessari."

    def has_permission(self, request, view):
        return IsOwnerOrClerk().has_permission(request, view)


class IsBusinessOperator(BasePermission):
    message = "Operazione riservata al personale autorizzato."

    def has_permission(self, request, view):
        return IsOwnerOrClerk().has_permission(request, view)
