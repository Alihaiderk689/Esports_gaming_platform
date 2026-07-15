from django.urls import path

from games import views

urlpatterns = [
    path('games/', views.GameListCreateView.as_view()),
    path('games/<int:pk>/', views.GameDetailView.as_view()),
]
