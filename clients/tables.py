import django_tables2 as tables

from .models import Client


class ClientTable(tables.Table):
    name = tables.Column(linkify=("client_edit", {"pk": tables.A("pk")}), verbose_name="Business")
    status = tables.TemplateColumn(
        '<span class="badge {% if record.status == "active" %}ok{% else %}warn{% endif %}">{{ record.get_status_display }}</span>'
    )
    actions = tables.TemplateColumn(
        template_code="""
        <a class="button small" href="{% url 'client_edit' record.id %}">Edit</a>
        <form method="post" action="{% url 'client_status' record.id 'suspended' %}" class="inline-form">{% csrf_token %}<button class="button small" type="submit">Suspend</button></form>
        <form method="post" action="{% url 'client_status' record.id 'active' %}" class="inline-form">{% csrf_token %}<button class="button small" type="submit">Reactivate</button></form>
        """,
        orderable=False,
        verbose_name="",
    )

    class Meta:
        model = Client
        fields = ("name", "owner_name", "email", "full_address", "status", "created_at", "actions")
        attrs = {"class": "data-table"}
