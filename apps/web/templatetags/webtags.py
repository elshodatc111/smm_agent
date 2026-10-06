from django import template

register = template.Library()


@register.filter
def get_item(d, key):
    """Hisobot shabloni: platforma rangi (topilmasa kulrang)."""
    try:
        return d.get(key, "#64748b")
    except AttributeError:
        return "#64748b"
