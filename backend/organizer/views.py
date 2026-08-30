from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit import log_action
from core.pagination import StandardResultsPagination
from organizer.models import Organizer
from organizer.serializers import (
    AdminOrganizerListSerializer,
    AdminOrganizerSerializer,
    AdminOrganizerUpdateSerializer,
    CnicUploadSerializer,
    CompanyUploadSerializer,
    OrganizerProfileSerializer,
    OrganizerProfileUpdateSerializer,
    OrganizerRegisterSerializer,
    OrganizerStatusSerializer,
)


def _get_organizer(user):
    try:
        return user.organizer_profile
    except Organizer.DoesNotExist:
        raise NotFound({'detail': 'You have not registered as an organizer yet.'})


def _reopen_review_after_document_change(organizer, actor, field_label):
    """An already-APPROVED organizer replacing their CNIC/company document
    would otherwise silently swap out the identity/compliance document the
    approval was actually based on, with no admin ever seeing the new one —
    see docs/EDGE_CASES.md's "organizer re-uploading ... after already being
    approved" entry. Sends the application back to PENDING so the new
    document gets the same admin review a fresh application would, exactly
    like resubmitting after a rejection. Deliberately a no-op for PENDING
    (already awaiting a first review) and REJECTED (re-uploading before
    resubmitting is the expected, unchanged flow — see
    OrganizerResubmitView) - only APPROVED -> PENDING is a real re-review
    event."""
    if organizer.status != Organizer.Status.APPROVED:
        return
    organizer.status = Organizer.Status.PENDING
    organizer.save(update_fields=['status', 'updated_at'])
    log_action(actor, 'organizer.compliance_document_replaced', organizer, document=field_label)


class OrganizerRegisterView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if Organizer.objects.filter(user=request.user).exists():
            raise ValidationError({'detail': 'You are already registered as an organizer.'})

        serializer = OrganizerRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organizer = serializer.save(user=request.user)
        return Response(OrganizerProfileSerializer(organizer).data, status=status.HTTP_201_CREATED)


class OrganizerUploadCnicView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        organizer = _get_organizer(request.user)
        serializer = CnicUploadSerializer(organizer, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _reopen_review_after_document_change(organizer, request.user, 'cnic_document')
        return Response(OrganizerProfileSerializer(organizer).data)


class OrganizerUploadCompanyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        organizer = _get_organizer(request.user)
        serializer = CompanyUploadSerializer(organizer, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _reopen_review_after_document_change(organizer, request.user, 'company_document')
        return Response(OrganizerProfileSerializer(organizer).data)


class OrganizerStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        organizer = _get_organizer(request.user)
        return Response(OrganizerStatusSerializer(organizer).data)


class OrganizerAcknowledgeStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        organizer = _get_organizer(request.user)
        organizer.last_seen_status = organizer.status
        organizer.save(update_fields=['last_seen_status'])
        return Response(OrganizerStatusSerializer(organizer).data)


class OrganizerResubmitView(APIView):
    """Puts a rejected application back in front of the admin. Only valid from
    'rejected' - a pending application is already awaiting review, and an
    approved one has nothing to resubmit. The applicant is expected to have
    already fixed whatever caused the rejection (editing profile fields /
    re-uploading documents via the existing endpoints, which don't check
    status) before calling this."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        organizer = _get_organizer(request.user)
        if organizer.status != Organizer.Status.REJECTED:
            raise ValidationError({'detail': 'Only a rejected application can be resubmitted.'})
        organizer.status = Organizer.Status.PENDING
        organizer.rejection_reason = ''
        organizer.last_seen_status = Organizer.Status.PENDING
        organizer.save(update_fields=['status', 'rejection_reason', 'last_seen_status'])
        return Response(OrganizerProfileSerializer(organizer).data)


class OrganizerProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        organizer = _get_organizer(request.user)
        serializer = OrganizerProfileUpdateSerializer(organizer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(OrganizerProfileSerializer(organizer).data)


class OrganizerDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        organizer = _get_organizer(request.user)
        return Response(OrganizerProfileSerializer(organizer).data)


class AdminOrganizerListView(generics.ListAPIView):
    serializer_class = AdminOrganizerListSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Organizer.objects.select_related('user').order_by('-created_at')
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset


class AdminOrganizerDetailView(generics.RetrieveUpdateAPIView):
    queryset = Organizer.objects.select_related('user')
    permission_classes = [permissions.IsAdminUser]

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return AdminOrganizerUpdateSerializer
        return AdminOrganizerSerializer

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return Response(AdminOrganizerSerializer(self.get_object(), context={'request': request}).data)
