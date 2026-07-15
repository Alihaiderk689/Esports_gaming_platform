from django.urls import path

from partners import views

urlpatterns = [
    path('partners/', views.PartnerListCreateView.as_view()),
    path('partners/<int:pk>/', views.PartnerDetailView.as_view()),
]
