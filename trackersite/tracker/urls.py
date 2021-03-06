# -*- coding: utf-8 -*-
from django.urls import include, path
from django.views.generic import DetailView

import tracker.views
from tracker import feeds
from tracker.models import Grant

urlpatterns = [
    path('tickets/', tracker.views.ticket_list, name='ticket_list'),
    path('tickets/page/<int:page>/', tracker.views.ticket_list, name='ticket_list'),
    path('ticket/watch/<int:pk>/', tracker.views.watch_ticket, name='watch_ticket'),
    path('tickets/feed/', feeds.LatestTicketsFeed(), name='ticket_list_feed'),
    path('tickets/feed/submitted/', feeds.SubmittedTicketsFeed(), name='ticket_submitted_feed'),
    path('ticket/<int:pk>/', tracker.views.ticket_detail, name='ticket_detail'),
    path('ticket/<int:pk>/sign/', tracker.views.sign_ticket, name='sign_ticket'),
    path('ticket/<int:pk>/edit/', tracker.views.edit_ticket, name='edit_ticket'),
    path('ticket/<int:pk>/edit/copypreexpeditures/', tracker.views.copypreexpeditures, name='copypreexpeditures'),
    path('ticket/<int:pk>/edit/docs/', tracker.views.edit_ticket_docs, name='edit_ticket_docs'),
    path('ticket/<int:pk>/edit/docs/new/', tracker.views.upload_ticket_doc, name='upload_ticket_doc'),
    path('ticket/<int:pk>/edit/<str:ack_type>/add/', tracker.views.ticket_ack_add, name='ticket_ack_add'),
    path('ticket/<int:pk>/edit/acks/<int:ack_id>/delete/', tracker.views.ticket_ack_delete, name='ticket_ack_delete'),
    path('ticket/<int:ticket_id>/docs/<str:filename>/', tracker.views.download_document, name='download_document'),
    path('ticket/new/', tracker.views.create_ticket, name='create_ticket'),
    path('ticket/<int:ticket_id>/media/show/', tracker.views.show_media, name='show_media'),
    path('ticket/<int:ticket_id>/media/update/', tracker.views.update_media, name='update_media'),
    path('ticket/<int:ticket_id>/media/manage/', tracker.views.manage_media, name='manage_media'),
    path('ticket/<int:ticket_id>/media/manage/success/', tracker.views.update_media_success, name='update_media_success'),
    path('ticket/<int:ticket_id>/media/manage/error/', tracker.views.update_media_error, name='update_media_error'),
    path('topics/', tracker.views.topic_list, name='topic_list'),
    path('topics/finance/', tracker.views.topic_finance, name='topic_finance'),
    path('topics/acks/', tracker.views.topic_content_acks_per_user, name='topic_content_acks_per_user'),
    path('topics/acks/acks.csv', tracker.views.topic_content_acks_per_user_csv, name='topic_content_acks_per_user_csv'),
    path('topic/<int:pk>/', tracker.views.topic_detail, name='topic_detail'),
    path('subtopic/<int:pk>/', tracker.views.subtopic_detail, name='subtopic_detail'),
    path('topic/watch/<int:pk>/', tracker.views.watch_topic, name='watch_topic'),
    path('topic/<int:pk>/feed/', feeds.TopicTicketsFeed(), name='topic_ticket_feed'),
    path('topic/<int:pk>/feed/submitted/', feeds.TopicSubmittedTicketsFeed(), name='topic_submitted_ticket_feed'),
    path('grants/', tracker.views.grant_list, name='grant_list'),
    path('grant/watch/<int:pk>/', tracker.views.watch_grant, name='watch_grant'),
    path('grant/<slug:slug>/', DetailView.as_view(model=Grant), name='grant_detail'),
    path('users/<str:username>/', tracker.views.user_detail, name='user_detail'),
    path('users/', tracker.views.user_list, name='user_list'),
    path('my/details/', tracker.views.user_details_change, name='user_details_change'),
    path('my/preferences/', tracker.views.preferences, name='preferences'),
    path('my/deactivate/', tracker.views.deactivate_account, name='deactivate_account'),
    path('transactions/', tracker.views.transaction_list, name='transaction_list'),
    path('transactions/feed/', feeds.TransactionsFeed(), name='transactions_feed'),
    path('transactions/transactions.csv', tracker.views.transactions_csv, name='transactions_csv'),
    path('cluster/<int:pk>/', tracker.views.cluster_detail, name='cluster_detail'),
    path('comments/', include('django_comments.urls')),
    path('admin/users/', tracker.views.admin_user_list, name='admin_user_list'),
    path('export/', tracker.views.export, name='export'),
    path('import/', tracker.views.importcsv, name='importcsv'),
    path('tickets/json/<str:lang>.json', tracker.views.tickets_json, name='tickets_json'),
    path('api/mediawiki/', tracker.views.mediawiki_api, name='mediawiki_api'),
    path('api/email_users', tracker.views.sendgrid_handler, name='sendgrid_handler'),
]
