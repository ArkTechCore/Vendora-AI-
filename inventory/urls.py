from django.urls import path

from . import views

urlpatterns = [
    path("vendors/", views.vendor_list, name="vendor_list"),
    path("vendors/new/", views.vendor_form, name="vendor_create"),
    path("vendors/<int:pk>/edit/", views.vendor_form, name="vendor_edit"),
    path("ingredients/", views.ingredient_list, name="ingredient_list"),
    path("ingredients/new/", views.ingredient_form, name="ingredient_create"),
    path("ingredients/<int:pk>/edit/", views.ingredient_form, name="ingredient_edit"),
    path("menu-items/", views.menu_item_list, name="menu_item_list"),
    path("menu-items/new/", views.menu_item_form, name="menu_item_create"),
    path("menu-items/<int:pk>/edit/", views.menu_item_form, name="menu_item_edit"),
    path("recipes/", views.recipe_form, name="recipe_create"),
    path("recipes/new/", views.recipe_form, name="recipe_create_legacy"),
    path("stock-movements/", views.stock_movement_list, name="stock_movement_list"),
    path("stock-movements/new/", views.stock_movement_form, name="stock_movement_create"),
    path("receives/", views.receive_list, name="receive_list"),
    path("purchases/", views.receive_list, name="purchase_list"),
    path("receives/new/", views.receive_form, name="receive_create"),
    path("receives/bulk/", views.bulk_receive, name="bulk_receive"),
    path("receives/items/new/", views.receive_item_form, name="receive_item_create"),
    path("counts/", views.inventory_count_list, name="inventory_count_list"),
    path("stock-count/", views.stock_count, name="stock_count"),
]
