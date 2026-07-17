from django.urls import path

from rag_chat import views


urlpatterns = [

    # ==========================
    # RuleBook APIs
    # ==========================

    path(
        "rules/",
        views.RuleBookListView.as_view(),
        name="rulebook-list"
    ),


    path(
        "rules/upload/",
        views.RuleBookUploadView.as_view(),
        name="rulebook-upload"
    ),


    path(
        "rules/<int:pk>/delete/",
        views.RuleBookDeleteView.as_view(),
        name="rulebook-delete"
    ),



    # ==========================
    # Chat APIs
    # ==========================

    path(
        "chat/",
        views.ChatView.as_view(),
        name="chat"
    ),


    path(
        "chat/history/",
        views.ChatHistoryView.as_view(),
        name="chat-history"
    ),

]