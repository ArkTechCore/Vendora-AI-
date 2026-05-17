from django.urls import path

from . import views

urlpatterns = [
    path("connections/", views.connection_list, name="pos_connection_list"),
    path("connections/new/", views.connection_form, name="pos_connection_create"),
    path("connections/<int:pk>/edit/", views.connection_form, name="pos_connection_edit"),
    path("connections/<int:pk>/sync/", views.sync_connection, name="pos_connection_sync"),
    path("sales/", views.sale_list, name="sale_list"),
    path("sales/manual/", views.manual_sales_entry, name="manual_sales_entry"),
    path("sales/new/", views.sale_form, name="sale_create"),
    path("sales/<int:pk>/edit/", views.sale_form, name="sale_edit"),
    path("sales/<int:pk>/process/", views.process_sale, name="sale_process"),
    path("sale-items/new/", views.sale_item_form, name="sale_item_create"),
]
