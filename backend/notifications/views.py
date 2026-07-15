from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import Notification
from notifications.serializers import MarkReadSerializer, NotificationSerializer


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)


class NotificationMarkReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated = Notification.objects.filter(
            recipient=request.user, id__in=serializer.validated_data['ids'],
        ).update(is_read=True)
        return Response({'detail': f'{updated} notification(s) marked as read.', 'updated': updated})


class NotificationMarkAllReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'detail': f'{updated} notification(s) marked as read.', 'updated': updated})


class NotificationDeleteView(generics.DestroyAPIView):
    queryset = Notification.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        notification = super().get_object()
        if notification.recipient_id != self.request.user.pk and not self.request.user.is_staff:
            raise PermissionDenied('You can only delete your own notifications.')
        return notification
