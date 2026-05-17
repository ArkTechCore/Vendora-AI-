import django_filters

from .models import Client


class ClientFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="search", label="Search")

    class Meta:
        model = Client
        fields = ["status", "q"]

    def search(self, queryset, name, value):
        return queryset.filter(name__icontains=value) | queryset.filter(owner_name__icontains=value) | queryset.filter(email__icontains=value)
