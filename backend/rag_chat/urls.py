from django.urls import path

from rag_chat import views

urlpatterns = [
    path('chat/', views.ChatView.as_view()),
    path('chat/history/', views.ChatHistoryView.as_view()),
    path('upload-rules/', views.RuleUploadView.as_view()),
    path('rules/', views.RuleListView.as_view()),
    path('rules/<int:pk>/', views.RuleDeleteView.as_view()),
]
