from rest_framework import generics, permissions

from games.models import Game
from games.permissions import IsAdminOrReadOnly
from games.serializers import GameSerializer


class GameListCreateView(generics.ListCreateAPIView):
    queryset = Game.objects.all()
    serializer_class = GameSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]


class GameDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Game.objects.all()
    serializer_class = GameSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]
