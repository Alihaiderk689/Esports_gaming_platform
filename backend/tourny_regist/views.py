from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from tourny_regist.models import Registration, Tournament
from tourny_regist.permissions import IsTournamentStaffOrAdmin
from tourny_regist.serializers import RegistrationCreateSerializer, RegistrationSerializer


class RegistrationCreateView(generics.CreateAPIView):
    serializer_class = RegistrationCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        registration = serializer.save()
        return Response(RegistrationSerializer(registration).data, status=status.HTTP_201_CREATED)


class RegistrationDeleteView(generics.DestroyAPIView):
    queryset = Registration.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        registration = super().get_object()
        if registration.player_id != self.request.user.pk and not self.request.user.is_staff:
            raise PermissionDenied('You can only cancel your own registration.')
        return registration


class MyRegistrationsView(generics.ListAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Registration.objects.filter(player=self.request.user).select_related('tournament', 'player')


class TournamentRegistrationsView(generics.ListAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def get_queryset(self):
        tournament = get_object_or_404(Tournament, pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, tournament)
        return Registration.objects.filter(tournament=tournament).select_related('tournament', 'player')


class RegistrationCheckInView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def patch(self, request, pk):
        registration = get_object_or_404(Registration.objects.select_related('tournament'), pk=pk)
        self.check_object_permissions(request, registration.tournament)

        if registration.checked_in:
            raise ValidationError({'detail': 'This registration is already checked in.'})

        registration.checked_in = True
        registration.checked_in_at = timezone.now()
        registration.save(update_fields=['checked_in', 'checked_in_at'])
        return Response(RegistrationSerializer(registration).data)
