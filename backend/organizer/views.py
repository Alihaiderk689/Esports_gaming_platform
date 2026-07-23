from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from organizer.models import Organizer
from organizer.serializers import (
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
        return Response(OrganizerProfileSerializer(organizer).data)


class OrganizerUploadCompanyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        organizer = _get_organizer(request.user)
        serializer = CompanyUploadSerializer(organizer, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
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
    serializer_class = AdminOrganizerSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Organizer.objects.select_related('user').order_by('-created_at')

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
