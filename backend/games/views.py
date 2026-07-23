from rest_framework import generics

from games.models import Category, Game
from games.permissions import IsAdminOrReadOnly
from games.serializers import CategorySerializer, GameSerializer


class GameListCreateView(generics.ListCreateAPIView):
    queryset = Game.objects.prefetch_related('categories').all()
    serializer_class = GameSerializer
    permission_classes = [IsAdminOrReadOnly]


class GameDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Game.objects.prefetch_related('categories').all()
    serializer_class = GameSerializer
    permission_classes = [IsAdminOrReadOnly]


class CategoryListCreateView(generics.ListCreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]


class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
