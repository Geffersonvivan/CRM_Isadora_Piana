import re
from django import template
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def sortable_th(context, field, label, width='', css_class=''):
    """Renderiza um <th> clicável para ordenação. `css_class` (opcional) permite
    marcar a coluna (ex.: 'col-nome' para congelá-la na planilha da Isadora)."""
    request = context.get('request')
    current_sort = context.get('current_sort', '')
    current_dir = context.get('current_dir', 'asc')

    params = request.GET.copy() if request else {}
    params.pop('page', None)

    if current_sort == field:
        new_dir = 'desc' if current_dir == 'asc' else 'asc'
        arrow = ' &uarr;' if current_dir == 'asc' else ' &darr;'
        style_extra = 'color:#002776;'
    else:
        new_dir = 'asc'
        arrow = ''
        style_extra = ''

    params['sort'] = field
    params['dir'] = new_dir
    url = '?' + params.urlencode()
    width_attr = f' style="width:{width};{style_extra}"' if width else (f' style="{style_extra}"' if style_extra else '')
    class_attr = f' class="{css_class}"' if css_class else ''
    return mark_safe(f'<th{class_attr}{width_attr}><a href="{url}" style="color:inherit;text-decoration:none;">{label}{arrow}</a></th>')


@register.filter
def whatsapp_link(telefone):
    if not telefone:
        return '-'
    numeros = re.sub(r'\D', '', telefone)
    if len(numeros) <= 11:
        numeros = '55' + numeros
    url = f'https://wa.me/{numeros}'
    telefone_safe = escape(telefone)
    return mark_safe(
        f'<a href="{url}" target="_blank" title="Abrir WhatsApp" '
        f'style="color:#374151;text-decoration:none;display:inline-flex;align-items:center;gap:4px;">'
        f'{telefone_safe}'
        f'<svg width="14" height="14" viewBox="0 0 24 24" fill="#25D366">'
        f'<path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/>'
        f'<path d="M12 0C5.373 0 0 5.373 0 12c0 2.625.846 5.059 2.284 7.034L.789 23.492a.75.75 0 00.917.918l4.462-1.494A11.945 11.945 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 22c-2.24 0-4.312-.724-5.994-1.952l-.418-.302-2.652.888.889-2.65-.303-.42A9.935 9.935 0 012 12C2 6.486 6.486 2 12 2s10 4.486 10 10-4.486 10-10 10z"/>'
        f'</svg></a>'
    )


@register.filter
def instagram_link(username):
    if not username:
        return '-'
    handle = re.sub(r'[^a-zA-Z0-9._]', '', username.lstrip('@'))
    username_safe = escape(username)
    url = f'https://instagram.com/{handle}'
    return mark_safe(
        f'<a href="{url}" target="_blank" title="Abrir Instagram" '
        f'style="color:#374151;text-decoration:none;display:inline-flex;align-items:center;gap:4px;">'
        f'{username_safe}'
        f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#E1306C" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<rect x="2" y="2" width="20" height="20" rx="5"/>'
        f'<circle cx="12" cy="12" r="5"/>'
        f'<circle cx="17.5" cy="6.5" r="1.5" fill="#E1306C" stroke="none"/>'
        f'</svg></a>'
    )


@register.filter
def contact_badge(ultima_interacao):
    """Retorna badge colorido com dias desde última interação."""
    if not ultima_interacao:
        return mark_safe('<span class="badge" style="background:#fee2e2;color:#991b1b;font-size:0.62rem;">Nunca</span>')
    now = timezone.now()
    delta = (now - ultima_interacao).days
    if delta <= 7:
        color, bg = '#166534', '#dcfce7'
        label = f'{delta}d'
    elif delta <= 30:
        color, bg = '#92400e', '#fef3c7'
        label = f'{delta}d'
    elif delta <= 60:
        color, bg = '#c2410c', '#ffedd5'
        label = f'{delta}d'
    else:
        color, bg = '#991b1b', '#fee2e2'
        label = f'{delta}d'
    return mark_safe(f'<span class="badge" style="background:{bg};color:{color};font-size:0.62rem;" title="{ultima_interacao:%d/%m/%Y}">{label}</span>')

@register.filter
def email_icon(email):
    """Ícone de e-mail: tooltip imediato com o endereço, clique copia."""
    if not email:
        return ''
    e = escape(email)
    return mark_safe(
        f'<button type="button" class="chan-icon" data-tip="{e}" onclick="copyChan(this, \'{e}\')">'
        f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
        f'<rect x="2" y="4" width="20" height="16" rx="2"/>'
        f'<path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg></button>'
    )


@register.filter
def instagram_icon(username):
    """Ícone do Instagram clicável (vazio quando não há perfil)."""
    if not username:
        return ''
    handle = re.sub(r'[^a-zA-Z0-9._]', '', username.lstrip('@'))
    u = escape(username)
    return mark_safe(
        f'<a href="https://instagram.com/{handle}" target="_blank" class="chan-icon" data-tip="{u}">'
        f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
        f'<rect x="2" y="2" width="20" height="20" rx="5"/>'
        f'<circle cx="12" cy="12" r="5"/>'
        f'<circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg></a>'
    )


@register.filter
def relacionamento_dot(obj):
    """Ponto colorido pela prioridade, com o detalhe completo no tooltip."""
    prio = getattr(obj, 'prioridade', '')
    partes = [f'Prioridade: {obj.get_prioridade_display()}']
    if hasattr(obj, 'get_grau_influencia_display'):
        partes.append(f'Influência: {obj.get_grau_influencia_display()}')
    if hasattr(obj, 'get_frequencia_relacionamento_display'):
        partes.append(f'Frequência: {obj.get_frequencia_relacionamento_display()}')
    cores = {'alta': '#dc2626', 'media': '#f59e0b', 'baixa': '#10b981'}
    cor = cores.get(prio, '#94a3b8')
    title = escape(' · '.join(partes))
    return mark_safe(f'<span class="prio-dot" style="background:{cor}" data-tip="{title}"></span>')
